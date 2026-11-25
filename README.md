# Shorts automaticos de reforma tributaria e educacao financeira

Sistema em Python que gera dois pacotes por dia para o YouTube Shorts:

- 07:00 em America/Cuiaba (11:00 UTC)
- 18:00 em America/Cuiaba (22:00 UTC)

Quando existe uma noticia verificada dos ultimos 24 horas, ela tem prioridade. Caso contrario, o sistema gera um resumo financeiro original baseado em conceitos gerais.

## Stack

- Python 3.11+
- RSS/Atom via `feedparser`
- SQLite para deduplicacao e historico
- Edge TTS para narracao gratuita
- Pillow para os slides verticais
- MoviePy para montar o MP4 1080x1920
- YouTube Data API v3 para upload opcional

## Instalacao

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

python -m pip install -e ".[video,test]"
cp .env.example .env
```

Nunca coloque credenciais em `config.yaml`, no codigo ou em commits. O modo padrao e `publish.auto_publish: false`, portanto o arquivo gera somente uma pasta em `output/` para revisao manual.

## Execucao local

```bash
python main.py --slot 07:00
pytest -q
```

O terminal mostra o roteiro, a fonte e o diretorio gerado. Dependendo da disponibilidade da rede e do TTS, o pacote pode conter slides PNG, audio MP3 e MP4.

## Configuracao

Edite `config.yaml` para:

- alterar fontes RSS;
- alterar palavras-chave;
- alterar horarios e fuso;
- trocar a janela de noticias;
- ligar ou desligar publicacao automatica;
- ajustar o limite de uploads.

As fontes iniciais incluem Receita Federal, Diario Oficial da Uniao, Agencia Brasil, Migalhas e JOTA. A disponibilidade real de RSS pode variar; a coleta falha com seguranca e registra o item no resultado, sem parar o restante.

## Producao no Google Cloud e YouTube

1. Crie um projeto em Google Cloud Console.
2. Ative **YouTube Data API v3**.
3. Configure a tela de consentimento OAuth.
4. Crie uma credencial OAuth do tipo **Desktop app**.
5. Execute o fluxo OAuth com as permissoes `youtube.upload` e salve o refresh token em `YOUTUBE_REFRESH_TOKEN`.
6. Configure no GitHub, em Settings > Secrets and variables > Actions:

```text
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN
```

Se as variaveis estiverem ausentes, o pipeline registra o aviso e continua em modo de revisao. Nenhuma credencial deve ir para o repositorio.

## Cota e publicacao

O modulo estima um upload em 1.600 unidades, respeita 10.000 unidades como limite padrao e limita uploads a dois por dia em `config.yaml`. O limite diario real pode variar pelo projeto; o painel de quotas do Google mostra o consumo definitivo.

Quando `auto_publish: true`, o upload criado fica privado inicialmente. O status, o ID, o link e o custo estimado ficam em SQLite, em `data/history.sqlite3`.

## GitHub Actions

`.github/workflows/shorts.yml` roda em:

- `0 11 * * *` = 07:00 em America/Cuiaba
- `0 22 * * *` = 18:00 em America/Cuiaba

O horario nao observa horario de verao em Cuiaba. O workflow gera slides, roteiro e artefatos em modo revisao por padrao.

Para ligar publicacao automatica:

1. Adicione e valide os tres secrets.
2. Configure `publish.auto_publish: true` no arquivo versionado.
3. Rode a analise manual.
4. Confirme que o canal esta elegivel para a API.

Para desligar:

```yaml
publish:
  auto_publish: false
```

## Seguranca editorial

As noticias usam somente fontes retornadas pelo RSS e precisam conter uma das palavras-chave configuradas. Noticias dos ultimos 24 horas sao comparadas por titulo e URL para evitar duplicidade.

Roteiros fiscais informam "conteudo informativo, consulte seu contador". A fonte primaria aparece no final dos slides e na descricao.

Os temas educacionais sao resumos originais de conceitos gerais. O projeto nao reproduz trechos protegidos por direitos autorais, nao apresenta livros como fato sem fonte e nao afirma vendas sem dados citados.

## Limitacoes conhecidas

- O canal precisa concluir qualquer verificacao exigida pelo YouTube.
- Credenciais, canal elegivel e consentimento OAuth sao configuracoes manuais.
- A cota de uploads e a disponibilidade da API pertencem ao Google.
- Monetizacao depende da elegibilidade do YouTube Partner Program e das regras da plataforma.
- A resolucao gerada atualmente e 1080x1920; nao represente como 4K.
- JOTA e Migalhas podem exigir autenticacao ou limitar feeds; adicione URLs reais na configuracao.
- O Edge TTS depende de disponibilidade externa e pode mudar por voz/idioma.
