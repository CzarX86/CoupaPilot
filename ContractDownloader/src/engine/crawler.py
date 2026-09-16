import asyncio
import hashlib
import json
import os
import platform
import re
import shutil
import time
import zipfile
from urllib.parse import unquote, urlparse
from typing import Optional, List, Dict, Any

import httpx

from src.db.session_db import SessionDB
from src.engine.parser import CoupaParser
from src.engine.coupa_metadata import CoupaMetadataExtractor
from src.engine.rate_limiter import RateLimiter
from src.db.coupa_metadata import CoupaMetadataRepository
from src.engine.tls import system_ssl_context
from src.auth.cookie_store import CookieStore, CookieStoreError, SecureSessionStore


class CoupaCrawler:
    def __init__(
        self,
        db: SessionDB,
        session_id: int,
        base_download_dir: str,
        base_url: str = "https://unilever.coupahost.com",
        cookies: Optional[Dict[str, str]] = None,
        concurrency: int = 11,
        request_delay: float = 0.03,
        timeout: float = 10.0,
        enable_circuit_breaker: Optional[bool] = None,
        preserve_existing_files: bool = False,
        metadata_repository: Optional[CoupaMetadataRepository] = None,
        cookie_store: Optional[CookieStore | SecureSessionStore] = None,
        diagnostic_log_path: Optional[str] = None,
        download_timeout: float = 60.0,
        download_attempts: int = 2,
        download_total_timeout: float = 300.0,
    ):
        self.db = db
        self.session_id = session_id
        self.base_download_dir = base_download_dir
        self.base_url = base_url.rstrip("/")
        self.concurrency = concurrency
        self.request_delay = request_delay
        self.timeout = timeout
        self.download_timeout = max(float(download_timeout), float(timeout))
        self.download_attempts = max(1, int(download_attempts))
        self.download_total_timeout = max(0.1, float(download_total_timeout))
        self.preserve_existing_files = preserve_existing_files
        self.cookie_store = cookie_store
        self.diagnostic_log_path = diagnostic_log_path or os.path.join(
            self.base_download_dir, "run_diagnostics.jsonl"
        )
        if metadata_repository is not None:
            self.metadata_repository = metadata_repository
        elif hasattr(db, "conn"):
            self.metadata_repository = CoupaMetadataRepository(db)
        else:
            # Lightweight crawler test doubles do not need persistence.
            self.metadata_repository = None
        if enable_circuit_breaker is None:
            disable_env = os.environ.get("COUPA_DISABLE_CIRCUIT_BREAKER", "").strip().lower()
            self.enable_circuit_breaker = disable_env not in {"1", "true", "yes", "on"}
        else:
            self.enable_circuit_breaker = bool(enable_circuit_breaker)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.rate_limiter = RateLimiter(base_delay=request_delay)

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.cookies = cookies or {}
        cookie_jar = httpx.Cookies()
        cookie_domain = urlparse(self.base_url).hostname or ""
        for name, value in self.cookies.items():
            cookie_jar.set(name, value, domain=cookie_domain, path="/")

        limits = httpx.Limits(max_keepalive_connections=concurrency, max_connections=concurrency * 2)
        self.client = httpx.AsyncClient(
            http2=True,
            cookies=cookie_jar,
            headers=self.headers,
            limits=limits,
            follow_redirects=True,
            timeout=httpx.Timeout(timeout),
            verify=system_ssl_context(),
        )

    def _po_url(self, po_number: str) -> str:
        order_number = po_number[2:] if po_number.upper().startswith(("PO", "PM")) else po_number
        return f"{self.base_url}/order_headers/{order_number}"

    async def _fetch_html(self, url: str, label: str = "") -> str:
        t0 = time.monotonic()
        async with self.semaphore:
            t_sem = time.monotonic()
            await self.rate_limiter.wait()
            t_rl = time.monotonic()
            response = await self.client.get(url)
            t_http = time.monotonic()
            if response.status_code == 429:
                self.rate_limiter.report_429()
                raise RateLimitError(f"Rate limited on {label or url}")
            if response.status_code in {401, 403}:
                raise SessionExpiredError(
                    f"Coupa returned HTTP {response.status_code} for {label or url}"
                )
            self.rate_limiter.report_success()
            response.raise_for_status()
            lowered_text = response.text.lower()
            if any(marker in lowered_text for marker in (
                "access denied",
                "you do not have permission",
                "not authorized to view",
                "insufficient privileges",
            )):
                raise AccessDeniedError(f"Coupa page denied access for {label or url}")
            final_url = str(response.url)
            if (
                "sessions/login" in final_url
                or "oauth" in final_url.lower()
                or "openid" in final_url.lower()
                or ("order_headers" not in final_url and "requisition_headers" not in final_url and "attachment" not in final_url.lower())
            ):
                raise AuthError(f"Auth failed on {label or url} — redirected to {final_url[:120]}")
            elapsed_total = (t_http - t0) * 1000
            if elapsed_total > 2000:
                print(f"[TIMING] _fetch_html {label}: total={elapsed_total:.0f}ms sem_wait={(t_sem - t0)*1000:.0f}ms rl_wait={(t_rl - t_sem)*1000:.0f}ms http={(t_http - t_rl)*1000:.0f}ms")
            return response.text

    @staticmethod
    def _is_valid_existing_file(path: str) -> bool:
        candidate = os.path.abspath(path)
        if not os.path.isfile(candidate) or os.path.getsize(candidate) <= 0:
            return False
        extension = os.path.splitext(candidate)[1].lower()
        if extension in {".xlsx", ".xlsm", ".docx", ".pptx", ".zip"}:
            return zipfile.is_zipfile(candidate)
        if extension == ".pdf":
            with open(candidate, "rb") as stream:
                return stream.read(5) == b"%PDF-"
        if extension in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}:
            try:
                from PIL import Image
                with Image.open(candidate) as image:
                    image.verify()
            except Exception:
                return False
        return True

    @staticmethod
    def _is_retryable_download_error(exc: Exception) -> bool:
        if isinstance(
            exc,
            (
                httpx.TimeoutException,
                httpx.NetworkError,
                RateLimitError,
                AttachmentTotalTimeoutError,
            ),
        ):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            response = getattr(exc, "response", None)
            return bool(
                response is not None
                and (response.status_code == 408 or 500 <= response.status_code <= 599)
            )
        return False

    async def _download_attachment(
        self,
        url: str,
        dest_path: str,
        *,
        replace_existing: bool = False,
    ) -> Dict[str, Any]:
        attachment_name = os.path.basename(dest_path)
        for attempt in range(1, self.download_attempts + 1):
            try:
                try:
                    result = await asyncio.wait_for(
                        self._download_attachment_once(
                            url,
                            dest_path,
                            replace_existing=replace_existing,
                        ),
                        timeout=self.download_total_timeout,
                    )
                except asyncio.TimeoutError as exc:
                    raise AttachmentTotalTimeoutError(
                        f"Download exceeded {self.download_total_timeout:g}s"
                    ) from exc
                result["attempt"] = attempt
                return result
            except Exception as exc:
                if attempt >= self.download_attempts or not self._is_retryable_download_error(exc):
                    raise
                self._write_diagnostic(
                    "download_retry",
                    attachment=attachment_name,
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    error_type=type(exc).__name__,
                    error_message=self._safe_error_detail(exc) or type(exc).__name__,
                )
                await asyncio.sleep(min(5.0, float(attempt)))

        raise RuntimeError("Attachment download attempts exhausted")

    async def _download_attachment_once(
        self,
        url: str,
        dest_path: str,
        *,
        replace_existing: bool = False,
    ) -> Dict[str, Any]:
        t0 = time.monotonic()
        async with self.semaphore:
            t_sem = time.monotonic()
            await self.rate_limiter.wait()
            t_rl = time.monotonic()
            async with self.client.stream(
                "GET",
                url,
                timeout=httpx.Timeout(
                    connect=self.timeout,
                    read=self.download_timeout,
                    write=self.download_timeout,
                    pool=self.timeout,
                ),
            ) as response:
                t_http = time.monotonic()
                if response.status_code == 429:
                    self.rate_limiter.report_429()
                    raise RateLimitError(f"Rate limited on download {url}")
                if response.status_code in {401, 403}:
                    raise SessionExpiredError(
                        f"Coupa returned HTTP {response.status_code} while downloading {url}"
                    )
                self.rate_limiter.report_success()
                response.raise_for_status()

                os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
                final_path = dest_path
                header_name = self._filename_from_content_disposition(
                    response.headers.get("content-disposition", "")
                )
                if header_name and not replace_existing:
                    safe_header_name = self._safe_attachment_filename(header_name, url)
                    if safe_header_name:
                        final_path = os.path.join(os.path.dirname(dest_path), safe_header_name)

                # Normal runs never overwrite. Individual retries replace only an
                # invalid file at the expected path; valid files are skipped before
                # reaching this method.
                if os.path.exists(final_path) and not replace_existing:
                    base, ext = os.path.splitext(final_path)
                    idx = 2
                    while os.path.exists(f"{base}_{idx}{ext}"):
                        idx += 1
                    final_path = f"{base}_{idx}{ext}"

                partial_path = f"{final_path}.part"
                received_bytes = 0
                content_length = response.headers.get("content-length")
                try:
                    with open(partial_path, "wb") as stream:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            stream.write(chunk)
                            received_bytes += len(chunk)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(partial_path, final_path)
                finally:
                    if os.path.exists(partial_path):
                        os.remove(partial_path)

                elapsed_total = (time.monotonic() - t0) * 1000
                if elapsed_total > 2000:
                    print(
                        f"[TIMING] _download: total={elapsed_total:.0f}ms "
                        f"sem_wait={(t_sem - t0)*1000:.0f}ms "
                        f"rl_wait={(t_rl - t_sem)*1000:.0f}ms "
                        f"http={(t_http - t_rl)*1000:.0f}ms bytes={received_bytes}",
                        flush=True,
                    )
                return {
                    "bytes": received_bytes,
                    "content_length": (
                        int(content_length)
                        if content_length and content_length.isdigit()
                        else None
                    ),
                    "duration_ms": int(elapsed_total),
                }

    def _write_diagnostic(self, event: str, **fields: Any) -> None:
        """Persist one support-safe, structured event for the current run."""
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
            "session_id": self.session_id,
            **fields,
        }
        try:
            parent = os.path.dirname(self.diagnostic_log_path) or "."
            os.makedirs(parent, exist_ok=True)
            with open(self.diagnostic_log_path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            # Diagnostics must never turn a PO failure into a second failure.
            pass

    @staticmethod
    def _safe_error_detail(exc: Exception) -> str:
        """Remove query strings from URLs before writing support logs."""
        detail = str(exc).strip()
        return re.sub(r"(https?://[^\s'\"?]+)\?[^\s'\"]*", r"\1?[redacted]", detail)

    def _format_exception(
        self,
        exc: Exception,
        *,
        phase: str,
        po_number: str,
        attachment: str = "",
        elapsed_ms: int = 0,
    ) -> str:
        """Keep exception type and execution context when a message is empty."""
        detail = self._safe_error_detail(exc)
        message = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
        context = [f"phase={phase}", f"po={po_number}"]
        if attachment:
            context.append(f"attachment={attachment}")
        if elapsed_ms:
            context.append(f"elapsed_ms={elapsed_ms}")
        if isinstance(exc, (httpx.TimeoutException, AttachmentTotalTimeoutError)):
            if isinstance(exc, AttachmentTotalTimeoutError):
                timeout = self.download_total_timeout
            else:
                timeout = self.download_timeout if phase == "download_attachment" else self.timeout
            context.append(f"timeout_s={timeout:g}")
        return f"{message} [{', '.join(context)}]"

    @staticmethod
    def _safe_attachment_filename(raw_name: str, download_url: str, max_component_len: int = 180) -> str:
        """Return a filesystem-safe filename with bounded length.

        Some Coupa pages render concatenated attachment text, producing names that exceed
        filesystem component limits on macOS (Errno 63). We keep a readable prefix,
        preserve extension when possible, and append a short hash for uniqueness.
        """
        sanitized = re.sub(r'[<>:"/\\|?*\s]+', '_', (raw_name or "")).strip("_")
        if not sanitized:
            sanitized = os.path.basename(download_url.split("?")[0]) or "attachment"
            sanitized = re.sub(r'[<>:"/\\|?*\s]+', '_', sanitized).strip("_") or "attachment"

        base, ext = os.path.splitext(sanitized)
        # Accept only short, simple extensions (.pdf, .xlsx, etc.).
        if not re.fullmatch(r"\.[A-Za-z0-9]{1,8}", ext or ""):
            ext = ""

        if not ext:
            url_base = os.path.basename(download_url.split("?")[0])
            _, url_ext = os.path.splitext(url_base)
            if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", url_ext or ""):
                ext = url_ext

        if len(sanitized) <= max_component_len:
            return sanitized

        digest = hashlib.sha1(sanitized.encode("utf-8")).hexdigest()[:10]
        suffix = f"_{digest}{ext}"
        keep = max(16, max_component_len - len(suffix))
        truncated_base = (base or "attachment")[:keep].rstrip("_")
        return f"{truncated_base}{suffix}"

    @staticmethod
    def _filename_from_content_disposition(content_disposition: str) -> str:
        if not content_disposition:
            return ""

        # RFC 5987 filename*=UTF-8''encoded-name.ext
        match_star = re.search(r"filename\*=([^;]+)", content_disposition, flags=re.IGNORECASE)
        if match_star:
            value = match_star.group(1).strip().strip('"')
            if "''" in value:
                _, value = value.split("''", 1)
            decoded = unquote(value)
            if decoded:
                return decoded

        # Legacy filename="name.ext"
        match_plain = re.search(r"filename=\"?([^\";]+)\"?", content_disposition, flags=re.IGNORECASE)
        if match_plain:
            return match_plain.group(1).strip()

        return ""

    async def preflight_company_access(
        self,
        company_pos: Dict[str, List[str]],
        sample_limit: int = 5,
    ) -> Dict[str, Dict[str, Any]]:
        """Sample Coupa pages per Company Code before starting downloads.

        A single denied page is not enough evidence: the sample is expanded
        up to ``sample_limit`` and only a consistently denied sample blocks
        the group.
        """
        results: Dict[str, Dict[str, Any]] = {}
        for company_code, po_numbers in company_pos.items():
            samples = list(dict.fromkeys(str(po) for po in po_numbers if po))[:sample_limit]
            denied = 0
            accessible = 0
            errors: list[str] = []
            for po_number in samples:
                try:
                    await self._fetch_html(self._po_url(po_number), label=f"preflight PO {po_number}")
                    accessible += 1
                except AccessDeniedError as exc:
                    denied += 1
                    errors.append(str(exc))
                except Exception as exc:
                    errors.append(type(exc).__name__)
            confirmed = bool(samples) and denied == len(samples)
            results[str(company_code)] = {
                "sampled": len(samples),
                "denied": denied,
                "accessible": accessible,
                "confirmed": confirmed,
                "errors": errors[:3],
            }
        return results

    async def process_po(self, po_number: str, company_code: str) -> Dict[str, Any]:
        """Process a single PO: check circuit breaker, fetch HTML, parse, download."""
        if self.enable_circuit_breaker:
            stats = self.db.get_company_stats(self.session_id, company_code)

            # Circuit Breaker: >= 15% progress, >= 3 POs processed, 100% error rate
            if stats["total"] > 0:
                progress_ratio = stats["processed"] / stats["total"]
                if progress_ratio >= 0.15 and stats["errors"] == stats["processed"] and stats["processed"] >= 3:
                    self.db.suspend_company_code(self.session_id, company_code)

        po_record = self.db.get_po(self.session_id, po_number)
        if po_record and po_record["status"] == "SKIPPED_VERIFICATION_REQUIRED":
            return {"po": po_number, "success": False, "error": "SKIPPED_VERIFICATION_REQUIRED"}

        po_dir_parts = [company_code]
        if po_record and po_record.get("output_subdir"):
            # output_subdir is stored with POSIX separators so sessions remain
            # portable. Accept legacy backslashes while creating a native path.
            po_dir_parts = [
                part
                for part in re.split(r"[\\/]+", str(po_record["output_subdir"]))
                if part not in {"", ".", ".."}
            ] or [company_code]
        po_dir = os.path.join(self.base_download_dir, *po_dir_parts, po_number)
        dir_created = False
        start_time = time.time()
        metadata_saved = False
        phase = "initializing"
        current_attachment = ""
        po_url = ""

        try:
            phase = "fetch_po_html"
            po_url = self._po_url(po_number)
            html_content = await self._fetch_html(po_url, label=f"PO {po_number}")

            if self.metadata_repository is not None:
                try:
                    phase = "extract_metadata"
                    metadata = CoupaMetadataExtractor.extract(
                        html_content,
                        po_number=po_number,
                        source_url=po_url,
                    )
                    self.metadata_repository.save(self.session_id, metadata)
                except Exception as metadata_error:
                    metadata_error_message = self._format_exception(
                        metadata_error,
                        phase="extract_metadata",
                        po_number=po_number,
                    )
                    self.metadata_repository.save_error(
                        self.session_id, po_number, metadata_error_message, po_url
                    )
                metadata_saved = True

            phase = "extract_po_attachments"
            po_attachments = CoupaParser.extract_attachments(html_content, base_url=self.base_url)

            all_attachments = list(po_attachments)
            pr_urls = CoupaParser.extract_pr_links(html_content)
            for pr_url in pr_urls:
                try:
                    phase = "fetch_pr_html"
                    full_pr_url = str(httpx.URL(self.base_url).join(httpx.URL(pr_url)))
                    pr_html = await self._fetch_html(full_pr_url, label=f"PR for {po_number}")
                    # Pass full PR page URL so relative attachment links resolve correctly
                    phase = "extract_pr_attachments"
                    pr_attachments = CoupaParser.extract_attachments(pr_html, base_url=full_pr_url)
                    all_attachments.extend(pr_attachments)
                except Exception as pr_error:
                    if isinstance(pr_error, AuthError):
                        raise
                    # Keep processing PO attachments even when one PR link fails.
                    pr_error_message = self._format_exception(
                        pr_error,
                        phase=phase,
                        po_number=po_number,
                    )
                    self._write_diagnostic(
                        "pr_error",
                        po=po_number,
                        phase=phase,
                        error_type=type(pr_error).__name__,
                        error_message=self._safe_error_detail(pr_error) or type(pr_error).__name__,
                        formatted_error=pr_error_message,
                    )
                    continue

            phase = "deduplicate_attachments"
            attachments = CoupaParser.deduplicate_attachments(all_attachments)
            clear_attachments = getattr(self.db, "clear_po_attachments", None)
            if clear_attachments:
                clear_attachments(self.session_id, po_number)

            if not attachments:
                phase = "persist_empty_success"
                self.db.update_po_status(self.session_id, po_number, "SUCCESS", None, 0, None)
                latency = time.time() - start_time
                return {"po": po_number, "success": True, "attachments": [], "latency": latency}

            phase = "prepare_download_directory"
            os.makedirs(po_dir, exist_ok=True)
            dir_created = True

            for att in attachments:
                phase = "download_attachment"
                current_attachment = self._safe_attachment_filename(
                    att.get("filename", ""), att.get("url", "")
                )
                dest_path = os.path.join(po_dir, current_attachment)
                if self.preserve_existing_files and self._is_valid_existing_file(dest_path):
                    download_info = {"bytes": os.path.getsize(dest_path), "attempt": 0}
                elif self.preserve_existing_files:
                    download_info = await self._download_attachment(
                        att["url"], dest_path, replace_existing=True
                    )
                else:
                    download_info = await self._download_attachment(att["url"], dest_path)
                digest = hashlib.sha256()
                try:
                    with open(dest_path, "rb") as attachment_stream:
                        for chunk in iter(lambda: attachment_stream.read(1024 * 1024), b""):
                            digest.update(chunk)
                    size_bytes = os.path.getsize(dest_path)
                    record_attachment = getattr(self.db, "record_po_attachment", None)
                    if record_attachment:
                        record_attachment(
                            self.session_id,
                            po_number,
                            current_attachment,
                            attachment_url=att.get("url"),
                            sha256=digest.hexdigest(),
                            size_bytes=size_bytes,
                            local_path=dest_path,
                            source_type="PO_OR_PR",
                        )
                except OSError:
                    # An attachment diagnostic must not turn a successful PO
                    # into an error; the download itself remains authoritative.
                    pass
                if isinstance(download_info, dict):
                    self._write_diagnostic(
                        "attachment_downloaded",
                        po=po_number,
                        attachment=current_attachment,
                        **download_info,
                    )

            phase = "persist_success"
            self.db.update_po_status(
                self.session_id, po_number, "SUCCESS", po_dir, len(attachments), None
            )
            latency = time.time() - start_time
            return {
                "po": po_number,
                "success": True,
                "attachments": attachments,
                "latency": latency,
            }

        except Exception as e:
            elapsed_ms = int(max(0.0, time.time() - start_time) * 1000)
            error_msg = self._format_exception(
                e,
                phase=phase,
                po_number=po_number,
                attachment=current_attachment,
                elapsed_ms=elapsed_ms,
            )
            self._write_diagnostic(
                "po_error",
                po=po_number,
                phase=phase,
                attachment=current_attachment or None,
                error_type=type(e).__name__,
                error_message=self._safe_error_detail(e) or type(e).__name__,
                formatted_error=error_msg,
                elapsed_ms=elapsed_ms,
                runtime={"os": platform.platform(), "python": platform.python_version()},
            )
            if self.metadata_repository is not None and not metadata_saved:
                try:
                    self.metadata_repository.save_error(
                        self.session_id,
                        po_number,
                        error_msg,
                        locals().get("po_url", ""),
                    )
                except Exception:
                    pass
            if dir_created and os.path.exists(po_dir) and not self.preserve_existing_files:
                shutil.rmtree(po_dir, ignore_errors=True)
            auth_required = isinstance(e, AuthError)
            # An expired session is a batch-level HIL pause, not a failed PO.
            # Keeping the row PENDING makes resume idempotent and preserves
            # completed POs without reprocessing them.
            self.db.update_po_status(
                self.session_id,
                po_number,
                "PENDING" if auth_required else "ERROR",
                None,
                0,
                error_msg if not auth_required else None,
            )
            if isinstance(e, AccessDeniedError) and not auth_required:
                self.db.set_po_access_diagnosis(self.session_id, po_number, "ACCESS_DENIED_CONFIRMED")
            return {
                "po": po_number,
                "success": False,
                "error": error_msg,
                "auth_required": auth_required,
                "diagnostic_log": self.diagnostic_log_path,
                "latency": time.time() - start_time,
            }

    async def process_batch(self, pos: List[tuple]) -> List[Dict[str, Any]]:
        """Process multiple POs concurrently. Each item is (po_number, company_code)."""
        tasks = [self.process_po(po, company) for po, company in pos]
        return await asyncio.gather(*tasks)

    async def close(self) -> None:
        if self.cookie_store:
            refreshed = {
                str(cookie.name): str(cookie.value)
                for cookie in self.client.cookies.jar
            }
            if refreshed.get("_coupa_session"):
                try:
                    self.cookie_store.save(refreshed)
                except CookieStoreError as exc:
                    print(f"[AUTH][WARNING] Refreshed Coupa session could not be cached: {exc}")
        await self.client.aclose()


class RateLimitError(Exception):
    pass


class AttachmentTotalTimeoutError(TimeoutError):
    pass


class AuthError(Exception):
    pass


class AccessDeniedError(Exception):
    """Coupa explicitly refused access to the requested PO page."""

    pass


class SessionExpiredError(AuthError):
    """The authenticated HTTP session was rejected by Coupa."""

    pass
