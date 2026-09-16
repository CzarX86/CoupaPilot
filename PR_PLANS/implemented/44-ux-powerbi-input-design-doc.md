# Design — UX do fluxo Power BI e isolamento do input

## Solução

1. O botão proxy do topo permanece acionável quando o botão da etapa está bloqueado por dados incompletos e chama um alerta contextual. O botão continua bloqueado quando a etapa ainda está fora do alcance da jornada.
2. O picker de suppliers recebe controles de busca no HTML. A consulta Power BI tokeniza termos, exige a presença de todos os tokens em UU/GU/S e ranqueia os resultados por correspondência textual e cobertura dos tokens.
3. O catálogo continua sendo descoberto pelo endpoint de metadados do dataset. A seleção do usuário é armazenada em `powerbi_po_column_selection_cache`, exposta pela `TurboAPI` e usada antes do fallback de `localStorage`.
4. Ao trocar a origem, o estado transitório do input anterior é limpo. Caches de catálogo e suppliers permanecem disponíveis como dados auxiliares, mas não são tratados como o input da nova execução.
5. `startRunFlow` define `runInProgress` e exibe `progress` antes das validações assíncronas e das chamadas de autenticação/importação; falhas devolvem o usuário à etapa correspondente.

## Compatibilidade

`localStorage` permanece como fallback para previews web e bridges antigos. O SQLite é a fonte persistente usada pela aplicação desktop.
