# Documento de Design: Aba Power BI isolada

## 1. Decisão de escopo

A integração será adicionada como uma nova tela da UI web do `ContractDownloader`. O código do pipeline Coupa existente não receberá dependências do Power BI nesta fase.

## 2. Componentes

### Frontend

- novo item de navegação `Power BI`;
- tela com cartões para conexão, suppliers, hierarquia e prévia;
- checkboxes para resultados de pesquisa e lista persistente de suppliers;
- árvore de Management Unit baseada nos caminhos retornados pelo dataset.

### Ponte Python

Novos métodos na subclasse `TurboAPI`:

- `get_powerbi_status()`;
- `start_powerbi_login()`;
- `search_powerbi_suppliers(term)`;
- `get_powerbi_supplier_cache()`;
- `save_powerbi_suppliers(suppliers)`;
- `remove_powerbi_supplier(uu)`;
- `validate_powerbi_supplier_cache()`;
- `get_powerbi_management_hierarchy()`.

Esses métodos serão mantidos fora de `AppAPI`, preservando o contrato atual usado pelo restante da aplicação.

### Cliente Power BI

Será criado um módulo pequeno e síncrono que:

1. localiza `fab` ou `uv` no ambiente local;
2. executa `fab api` com o arquivo JSON de consulta;
3. interpreta somente JSON de resposta;
4. nunca inspeciona ou grava tokens/cookies;
5. retorna erros operacionais sem expor o corpo de autenticação.

O cache de autenticação continua sendo gerenciado pelo Fabric CLI/MSAL. A aplicação não copiará nem interpretará esse cache.

## 3. Dados locais

O catálogo ficará em:

`~/.contract_downloader/powerbi_supplier_cache.json`

O arquivo conterá apenas nomes, aliases, códigos UU, origem e estado de validação. Os códigos prioritários iniciais serão marcados como provisórios até confirmação do usuário.

O código UU será tratado como string opaca. O prefixo observado `WCSCUU` não será usado como regra de validação.

## 4. Consultas

### Suppliers

A pesquisa consulta os níveis `SupplierHierarchyUU`, `SupplierHierarchyGU` e `SupplierHierarchyS`. A UI agrupa os resultados por UU e mostra o nome oficial e os códigos relacionados quando disponíveis.

### Management Unit

A hierarquia será consultada sem `Time[Year]` e sem filtros de supplier:

- Management Unit L1 Name;
- Management Unit L2 Name;
- Management Unit L3 Name;
- Management Unit L4 Name;
- Management Unit L5 Name;
- Management Unit L6 Name.

As medidas de Commitment e Goods Received serão usadas para preservar a semântica de não vazio quando o modelo exigir. A UI monta a árvore localmente a partir dos caminhos completos.

## 5. Validação e falhas

- código presente → estado validado;
- código ausente → estado inválido e alerta visível;
- Power BI indisponível → dados locais continuam visíveis com estado “não validado”;
- ausência de login → a tela orienta o usuário a autenticar e não bloqueia o restante do app;
- erro de consulta → mensagem resumida na aba, sem corpo de token ou cookies.

## 6. Build macOS

O build existente em `ContractDownloader/build.py` continuará sendo usado. Os assets da nova aba serão incluídos pelo mesmo `--add-data` já utilizado para `src/gui/web`.

Comando de validação:

```bash
UV_CACHE_DIR=/tmp/coupa-contract-uv-cache uv run --group build python build.py --macos
```

O cliente `fab` será descoberto em runtime. Para o teste local, o ambiente pode usar a instalação oficial `ms-fabric-cli` disponível via `uv`.
