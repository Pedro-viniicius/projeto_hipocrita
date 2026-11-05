# Especificação de UI/UX: Vitrine "Pão de Cada Dia" (MVP)

Brief: `docs/produto/briefs/vitrine-mvp.md` (CA1 a CA20). Identidade: `docs/produto/identidade/`. Rodada 1. Esta spec passa das 300 linhas de propósito: cobre 9 telas, tokens e microcopy. Independente de framework: HTML semântico, classes `.componente` e custom properties em um CSS único. Nada aqui depende de JavaScript; onde há JS, é melhoria opcional.

## Objetivo e usuário

Estudantes e comunidade da UFLA Campus Paraíso (MG), quase sempre no celular, com pressa entre aulas, conexão às vezes ruim, familiaridade média com tecnologia. O visitante precisa saber em segundos: o que é, quanto custa, se está disponível, onde e quando pegar, como falar com quem vende. O vendedor (estudante que hoje anuncia no grupo de WhatsApp) precisa manter o anúncio em dia com um ou dois toques.

Tom: cotidiano, curto, sem jargão, sem promessa de venda, sem urgência falsa, sem contadores.

## Fluxo

1. Visitante: Início (busca, categoria, "Disponíveis hoje") → Oferta (escolhe variação) → "Consultar no WhatsApp" (abre WhatsApp; nada é pedido confirmado) → volta à lista no mesmo ponto. Atalhos: Oferta → Vendedor; Oferta → Denunciar.
2. Vendedor: Cadastrar/Entrar → Meus anúncios → Adicionar anúncio (formulário) → "Aguardando aprovação" (primeiro anúncio) ou publicado → no dia a dia: "Confirmar disponível hoje", pausar, esgotado, vendido, editar. Perfil: dados, autorização do WhatsApp, excluir conta.
3. Administração: Aprovações → Denúncias → Anúncios (ocultar) → Categorias.

Mapa de rotas sugerido (o `arquiteto` decide os caminhos finais): `/`, `/oferta/<id>`, `/oferta/<id>/whatsapp` (GET, redireciona), `/oferta/<id>/denunciar`, `/vendedor/<slug>`, `/entrar`, `/cadastrar`, `/meus-anuncios`, `/meus-anuncios/novo`, `/meus-anuncios/<id>/editar`, `/perfil`, `/perfil/excluir-conta`, `/admin/...`.

## 1. Tokens (custom properties)

```css
:root {
  /* Cores da marca */
  --azul-lavras:#1F4171; --azul-lavras-700:#17325A; --azul-50:#E8EEF7;
  --verde-campus:#06713F; --verde-campus-700:#055C34; --verde-50:#E3F2EA;
  --noite-ictin:#050C45; --ciano-circuito:#2EC4EA;      /* ciano só sobre Noite ICTIN */
  /* Neutros */
  --tinta:#0F1A2E; --grafite:#4A5468; --nevoa:#E4E9F0; --papel:#F5F7FA; --branco:#FFFFFF;
  --borda-campo:#7B8499;            /* 3,75:1 sobre branco (WCAG 1.4.11); Névoa não basta */
  /* Estados */
  --ambar:#9A5B00; --ambar-50:#FFF4E0; --vermelho:#B42318; --vermelho-50:#FDECEA; --vermelho-700:#8E1B12;
  /* Semânticos */
  --fundo:var(--papel); --superficie:var(--branco); --texto:var(--tinta); --texto-apoio:var(--grafite);
  --acao:var(--azul-lavras); --acao-hover:var(--azul-lavras-700); --preco:var(--verde-campus);
  --linha:var(--nevoa); --foco:var(--azul-lavras); --foco-sobre-azul:var(--branco);
  /* Tipografia */
  --fonte-titulo:"Barlow Condensed","Arial Narrow","Roboto Condensed",system-ui,sans-serif;
  --fonte-texto:"Source Sans 3",system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
  /* Espaços (4·8·12·16·24·32·48) */
  --e1:.25rem; --e2:.5rem; --e3:.75rem; --e4:1rem; --e5:1.5rem; --e6:2rem; --e7:3rem;
  /* Raios */
  --r-selo:8px; --r-botao:12px; --r-campo:12px; --r-cartao:16px; --r-chip:999px;
  /* Outros */
  --toque:2.75rem;                  /* 44 px, alvo mínimo */
  --campo-altura:3rem;              /* 48 px */
  --borda:1px solid var(--linha);   /* cartões: borda, não sombra */
  --sombra:none;                    /* quase nula; só 0 1px 0 rgba(15,26,46,.06) em menus <details> */
  --contorno-foco:3px solid var(--foco); --contorno-foco-offset:2px;
  --halo-campo:0 0 0 4px var(--azul-50);   /* decorativo; o sinal de foco é a borda + contorno */
  --largura-max:70rem;              /* 1120 px */
  --largura-texto:40rem;            /* ~65 caracteres */
}
```

Em `@media (min-width:37.5em)` e `(min-width:60em)` (600 e 960 px) só muda layout, não tokens, exceto tamanhos de título abaixo.

### Escala tipográfica (px; no CSS use `rem`, 16 px = 1rem, para respeitar o zoom do usuário)

| Papel (classe) | Família / peso | Tamanho / altura | Notas |
|---|---|---|---|
| `.t-display` (só em 404/erro no desktop) | Barlow Cond. 700 | 48/48 | opcional; use `.t-1` se quiser menos tamanhos |
| `.t-1` (h1 de página) | Barlow Cond. 600 | 32/36 mobile, 40/44 a partir de 960 | identidade pede 40/44; 32 no celular evita quebra |
| `.t-2` (h2 de seção) | Barlow Cond. 600 | 24/28 mobile, 28/32 desktop | |
| `.rotulo` (rótulos de seção, abas, tags) | Barlow Cond. 600, caixa alta, `letter-spacing:.14em` | 14/16 | cor Azul Lavras ou Grafite |
| `.texto` corpo | Source Sans 3 400 | 17/24 | |
| `.texto-forte` nome e ênfase | Source Sans 3 600 | 17/24 | nome do produto no cartão |
| `.legenda` | Source Sans 3 400 | 14/20 | apoio, dica de campo; cor Grafite |
| `.preco` | Source Sans 3 700, `font-variant-numeric:tabular-nums` | 22/24 | cor Verde Campus |
| `.botao` | Source Sans 3 600 | 17/24 | |
| `.selo` | Source Sans 3 600 | 14/20 | |

Não use caixa alta fora de `.rotulo`. Texto corrido máx. `--largura-texto`.

### Verificação de contraste (calculada, razão de contraste WCAG)

| Uso | Texto / fundo | Razão | Ok |
|---|---|---|---|
| Texto principal | Tinta / Branco · Papel · Névoa | 17,4 · 16,2 · 14,3 | sim |
| Texto de apoio, placeholder, legenda | Grafite / Branco · Papel · Névoa · Azul 50 | 7,6 · 7,1 · 6,2 · 6,5 | sim |
| Botão primário, cabeçalho | Branco / Azul Lavras | 10,2 | sim |
| Botão confirmar (verde) | Branco / Verde Campus | 6,1 | sim |
| Preço, link verde | Verde Campus / Branco · Papel · Verde 50 | 6,1 · 5,7 · 5,3 | sim |
| Link e rótulo azul | Azul Lavras / Branco · Papel · Azul 50 · Névoa | 10,2 · 9,5 · 8,8 · 8,4 | sim |
| Selo Esgotado, aviso de atenção | Âmbar / Âmbar 50 · Branco | 5,0 · 5,4 | sim |
| Erro, botão perigo | Vermelho / Vermelho 50 · Branco · Papel; Branco / Vermelho | 5,8 · 6,6 · 6,1; 6,6 | sim |
| Texto sobre faixa escura | Ciano / Noite ICTIN; Branco / Noite | 8,9; 18,3 | sim |
| Subtítulo no cabeçalho | Névoa / Azul Lavras | 8,4 | sim |
| Contorno de foco | Azul Lavras / Papel · Branco; Branco / Azul Lavras (no cabeçalho) | 9,5 · 10,2; 10,2 | sim (≥ 3:1) |
| Borda de campo, chip, rádio | Borda campo / Branco | 3,75 | sim (≥ 3:1) |

Regras: ciano nunca sobre Branco/Papel (2,1:1) nem sobre Azul Lavras (5,0:1 só serve para texto grande; evitar). Verde e âmbar nunca são o único sinal: sempre ícone + palavra. Em `Vendido`, preço em Grafite riscado (`text-decoration:line-through`), não verde.

### Foco, hover, movimento

- `:focus-visible{outline:var(--contorno-foco);outline-offset:var(--contorno-foco-offset)}` em tudo que recebe foco. Dentro do cabeçalho azul: `outline-color:var(--foco-sobre-azul)`. Nunca `outline:none` sem substituto.
- Campo em foco: borda 2 px Azul Lavras + `--halo-campo` + o contorno acima.
- Hover só em `@media (hover:hover)`: botão azul → `--azul-lavras-700`; verde → `--verde-campus-700`; cartão → borda Azul Lavras e título sublinhado. Nada depende do hover.
- Transições só de cor, 120 ms, dentro de `@media (prefers-reduced-motion:no-preference)`. Sem carrossel, sem animação de entrada, sem skeleton animado.

### Fontes

Self-host em `/static/fontes/` (licença SIL OFL: incluir `OFL.txt`): `barlow-condensed-500|600|700.woff2` e `source-sans-3-400|600|700.woff2`. Subconjunto: U+0020-007E, U+00A0-00FF (acentos do português), U+2013-2014, U+2018-201D, U+2022, U+2026 (`pyftsubset` ou `glyphhanger`). `@font-face{font-display:swap}` em cada peso, `font-style:normal`. `<link rel="preload" as="font" type="font/woff2" crossorigin>` só para `source-sans-3-400` e `barlow-condensed-600`. Fallback de sistema nas variáveis `--fonte-*`; o texto aparece de imediato e troca ao carregar. Zero chamada ao Google em tempo de execução.

## 2. Componentes

Todos novos (projeto vazio). Onde ficam: CSS único (ex.: `static/css/app.css`, seções na ordem: tokens, base, layout, componentes, utilitários) e parciais de template. Estados padrão de todos os alvos clicáveis: foco (acima), hover (acima), desabilitado, e erro quando for campo.

### 2.1 Estrutura da página
`<body>` → `a.pular` → `header.cabecalho` → `main#conteudo tabindex="-1"` → `footer.rodape`. `html lang="pt-BR"`. `<title>` = "<Tela> · Pão de Cada Dia"; em erro de formulário, "Erro: <Tela> · …". Um só `h1` por página.
- `a.pular`: primeiro elemento focável; fora da tela até receber foco, aí fixo no topo esquerdo, fundo Branco, texto Azul, 44 px. Texto "Pular para o conteúdo". Leva a `#conteudo`.
- `.container`: `max-width:var(--largura-max)`, padding lateral 16 px (24 px a partir de 600).

### 2.2 Cabeçalho e logo
- Início: faixa Azul Lavras com logo (símbolo 32 px + texto "PÃO DE CADA DIA", Barlow Cond. 700, 22/24, caixa alta, Branco), abaixo `.legenda` Névoa: "Compra e venda entre estudantes · Campus Paraíso · MG", o `h1` "O que tem no campus hoje?" (`.t-1`, Branco) e a busca, tudo na mesma faixa (como a página 5 do PDF). Sem banner, sem imagem.
- Demais páginas: barra azul compacta (56 px) só com logo.
- Direita (todas as páginas): um link de 44 px, Branco, sublinhado no foco/hover: visitante "Vender aqui" → `/entrar`; vendedor logado "Meus anúncios" (+ "Sair" no rodapé e no Perfil); admin "Administração".
- Logo é um `<a href="/">` com `aria-label="Pão de Cada Dia, ir para o início"`. O texto visível já nomeia; o SVG tem `aria-hidden="true"`.
- SVG (símbolo 48×48, `fill:currentColor`; recriar com refinamento se quiser; três pontos = miolo/“digitando…”):
```html
<svg viewBox="0 0 48 48" aria-hidden="true" focusable="false" class="logo">
  <rect x="4" y="4" width="40" height="20" rx="10"/>
  <rect x="10" y="16" width="28" height="22" rx="4"/>
  <path d="M10 32 L8 44 L21 38 Z"/>
  <g class="pontos" fill="var(--logo-ponto,#fff)"><circle cx="17" cy="28" r="2.5"/><circle cx="24" cy="28" r="2.5"/><circle cx="31" cy="28" r="2.5"/></g>
</svg>
```
  Em fundo azul: `color:#fff; --logo-ponto:var(--azul-lavras)`. Em fundo claro: `color:var(--azul-lavras); --logo-ponto:#fff`. Abaixo de 24 px (favicon): `.logo--mini .pontos{display:none}`. Área de proteção: 4 px ao redor. Favicon e ícone do app: o símbolo sobre quadrado Azul Lavras, raio 12 (arquivos SVG/PNG estáticos).

### 2.3 Busca
`<form role="search" method="get" action="/">` com `label` visível "Buscar" ou, como na referência, rótulo visualmente oculto "Buscar produto, serviço ou vendedor" (`.so-leitor`) mais o placeholder. Campo branco 48 px, raio 12, ícone lupa à esquerda (decorativo), `type="search"`, `name="q"`, `autocomplete="off"`, `enterkeyhint="search"`. Botão "Buscar" (primário, 48 px) à direita, **sempre visível** (sem JS não há "buscar ao digitar"). Campos ocultos repetem `cat` e `hoje` para a busca manter filtros. Placeholder: "Bolo, apostila, aula particular…" (Grafite). Valor atual repovoado. Em foco: ver tokens. No cabeçalho azul o foco usa contorno Branco.

### 2.4 Chips de categoria e filtro "Disponíveis hoje"
- `nav aria-label="Categorias"` com `<ul>` de links (`<a>`), não botões: funcionam sem JS e mantêm `q` e `hoje` nos `href`. Itens: Tudo, Comidas e doces, Bebidas, Serviços, Objetos e usados, Outros (vindas do banco, editáveis). Quebram em linhas (sem rolagem horizontal escondendo opções).
- Chip: 44 px de altura, padding 0 16, raio 999, borda 1 px `--borda-campo`, fundo Branco, texto Tinta 600. Ativo: fundo Azul Lavras, texto Branco, `aria-current="true"`, e ícone check (16 px) antes do texto (não só cor).
- "Disponíveis hoje": link separado abaixo dos chips, mesmo tamanho, com ícone de sol/relógio; estado ativo: fundo Verde 50, borda 2 px Verde Campus, texto Verde, ícone check + `aria-current="true"`; clicar de novo remove o filtro. Lê-se como filtro à parte ("combina com a categoria").
- Desabilitado: não existe (sempre clicável). Hover: borda Azul Lavras.

### 2.5 Cartão de oferta (`.cartao-oferta`)
Elemento `<article>` com `id="oferta-<id>"` contendo um único `<a href="/oferta/<id>?<filtros atuais>">` que cobre o cartão (técnica: o `<a>` envolve o título e `::after{position:absolute;inset:0}` estende a área; nada clicável aninhado). O nome do link é o título da oferta; o resto do texto fica fora do nome acessível mas dentro do cartão (para leitor de tela: título, depois preço, estado, vendedor e retirada na leitura linear do `<article>`).

**Decisão: o cartão não tem botão secundário.** Motivos: o brief permite "no máximo um"; o único candidato, "Consultar no WhatsApp", precisa de variação e do aviso de "não é pedido confirmado", que só cabem na página da oferta; um botão no cartão competiria com o link do cartão inteiro e geraria mensagem sem variação. A "ação principal clara" é o próprio cartão, sinalizado por uma linha de rodapé não interativa "Ver oferta" + ícone seta (`.cartao-acao`, Azul 600, 17 px).

Anatomia, ordem do DOM (= hierarquia: produto, preço, disponibilidade, retirada, ação):
1. foto (`<img>` com `alt=""` quando o título já está ao lado, `width/height`, `loading="lazy"`, `decoding="async"`, `object-fit:cover`; as 2 primeiras da lista `loading="eager"`, sem `fetchpriority` extra) ou placeholder (2.12);
2. título `.texto-forte`, até 2 linhas, resto com reticências (`-webkit-line-clamp:2`);
3. preço `.preco` (com `.legenda` "A partir de" acima quando houver variações de preço diferente);
4. selo de estado (2.6);
5. `.legenda`: "Ana B. · retirada no bloco 3 às 10h" (vendedor · resumo de retirada ou entrega, até 2 linhas);
6. "Ver oferta →".
Layout mobile (< 600 px): linha horizontal, foto quadrada 112 px à esquerda (raio 12), texto à direita; cartão Branco, borda `--borda`, raio 16, padding 12, espaço 12 entre cartões. A partir de 600 px: cartão vertical, foto 4:3 no topo ocupando a largura, texto abaixo com padding 16; grade de 2 colunas (600–959) e 3 (≥ 960), espaço 16/24.
Estados: foco (contorno 3 px ao redor do cartão, arredondado), hover (borda azul), `Vendido`/`Esgotado` (não reduzir opacidade: baixaria o contraste do texto; só o preço e o selo mudam), conteúdo longo (título em 2 linhas, vendedor com reticências).

### 2.6 Selos de estado (`.selo`)
Pílula de 28 px, padding 4×8, raio 8, ícone 16 px + texto, nunca só cor. Texto sempre presente em pt-BR.

| Selo | Quem vê | Cores (texto / fundo) | Ícone |
|---|---|---|---|
| Disponível hoje | público | Verde / Verde 50 | `circulo-check` |
| Sob encomenda | público | Azul Lavras / Azul 50 | `relogio` |
| Esgotado | público | Âmbar / Âmbar 50 | `circulo-menos` |
| Vendido | público | Grafite / Névoa | `etiqueta-check`; preço riscado |
| Pausado | só vendedor | Grafite / Névoa, borda 1 px Grafite tracejada | `pausa` |
| Precisa de confirmação | só vendedor | Âmbar / Âmbar 50, borda 1 px Âmbar | `alerta-circulo` |
| Aguardando aprovação | só vendedor | Azul Lavras / Azul 50, borda 1 px Azul tracejada | `ampulheta` |

Se nenhum estado público se aplica (ex.: oferta do dia sem confirmação de hoje), o cartão não mostra selo (nada de "Indisponível"). Os selos só do vendedor nunca aparecem em página pública nem em HTML público.

### 2.7 Botões (`.botao`)
Altura mínima 48 px (nunca menos que 44), padding 0 24, raio 12, Source Sans 600 17, ícone opcional 20 px à esquerda, largura total no mobile em ação principal.
- `.botao--primario`: Azul Lavras / Branco (hover 700). Usos: Consultar no WhatsApp, Adicionar anúncio, Entrar, Salvar e publicar.
- `.botao--secundario`: Branco, borda 2 px Azul Lavras, texto Azul. Usos: Editar, Cancelar, Limpar filtros.
- `.botao--confirmar`: Branco, borda 2 px Verde Campus, texto Verde (hover: fundo Verde 50). Uso: "Confirmar disponível hoje", "Aprovar". Fica fora do destaque do "Adicionar anúncio".
- `.botao--perigo`: Vermelho / Branco. Uso: "Excluir minha conta para sempre".
- `.botao--link`: sem fundo, texto Azul sublinhado, 44 px de área. Usos: ações discretas, "Denunciar esta oferta".
- Desabilitado (só quando de fato inútil, e prefira ocultar): fundo Névoa, texto Grafite, `cursor:not-allowed`, atributo `disabled`. Em envio (com JS): texto troca para "Salvando…", `aria-disabled="true"`; sem JS o navegador já mostra o carregamento.
- Erro: botão nunca muda de cor por erro; o erro aparece na mensagem.
- Botões de ação em lista (POST) são `<button>` dentro de `<form method="post">` com token CSRF; navegação é `<a>`.

### 2.8 Campos de formulário (`.campo`)
Estrutura: `<div class="campo"><label for="x">Título <span class="opcional">(opcional)</span></label><p id="x-dica" class="legenda">Exemplo: …</p><input id="x" aria-describedby="x-dica x-erro"><p id="x-erro" class="erro">…</p></div>`.
- Rótulo sempre visível acima (nunca só placeholder), Source Sans 600 17. Obrigatórios sem marca; opcionais com "(opcional)" em 400 Grafite. No topo do formulário: "Campos sem “(opcional)” são obrigatórios."
- Dica `.legenda` com exemplo de preenchimento ("Exemplo: Bolo de pote de ninho com morango"). O placeholder **não** carrega informação essencial; pode repetir o exemplo em Grafite.
- Campo: 48 px (textarea mín. 96 px), fundo Branco, borda 1 px `--borda-campo`, raio 12, padding 0 16, texto Tinta 17. `inputmode`/`autocomplete` adequados (e-mail, `tel`, senha `current-password`/`new-password`).
- Erro: borda 2 px Vermelho, `aria-invalid="true"`, mensagem abaixo com ícone `alerta-triangulo` + texto Vermelho 14/20 ("O que houve. Como resolver."). A cor nunca é o único sinal.
- Resumo de erros no topo do `main` (`.aviso--erro`, `role="alert"`): "Corrija 2 campos para continuar." + lista de links âncora para cada campo. A página reexibe tudo preenchido (exceto senha e arquivos).
- Rádios e caixas de seleção: controle nativo 24 px (`accent-color:var(--azul-lavras)`) dentro de `<label>` com linha de 44 px de altura; `<fieldset><legend>` para grupos. Selecionável por cartão: `.opcao` com borda 1 px, raio 12, selecionada borda 2 px Azul + fundo Azul 50.
- Select nativo estilizado como campo (sem biblioteca).
- Desabilitado/somente leitura: fundo Papel, texto Grafite, sem halo.

### 2.9 Mensagens de feedback (`.aviso`)
Caixa com ícone 24 px + texto, raio 12, padding 12×16, borda 1 px da mesma matiz. `role="status"` (sucesso, informação) ou `role="alert"` (erro). Persistente até a próxima navegação (nada de toast que some). Sempre no topo do `main`, antes do `h1`, e a página carrega com o foco no `main` (`tabindex="-1"`) para leitores de tela lerem.
- Sucesso: Verde 50 / texto Tinta, ícone `circulo-check` Verde. Informação: Azul 50, ícone `info`. Atenção: Âmbar 50, ícone `alerta-triangulo` Âmbar. Erro: Vermelho 50, ícone `alerta-circulo` Vermelho.
- Texto em Tinta (≥ 14:1) para leitura; a matiz só aparece em borda e ícone.
- Padrão pós-ação do vendedor: redirecionar para a lista com a mensagem e âncora `#anuncio-<id>`.

### 2.10 Aviso do WhatsApp (`.aviso-contato`)
Logo abaixo do botão de contato, `.legenda` com ícone `info`: "Abrir o WhatsApp não é um pedido confirmado. Disponibilidade, pagamento e entrega são combinados direto com quem vende." Nunca escondido em tooltip.

### 2.11 Bloco de alimento (`dl.alimento`)
Só em categoria Comidas e doces. `<dl>` com pares: Porção, Ingredientes, Alergênicos (`dt` `.rotulo`, `dd` texto). Campo vazio mostra "Não informado pelo vendedor" em Grafite itálico, nunca omitido nem deduzido. Cabeçalho `h2.t-2` "Sobre este alimento". Nota `.legenda`: "Informado por quem vende. Confirme com a pessoa se tiver alergia."

### 2.12 Placeholder de imagem ausente (`.foto-vazia`)
Bloco Névoa com o ícone `imagem` 32 px em Grafite centralizado e a legenda "Sem foto" (só na página da oferta; no cartão apenas o ícone). Mesma proporção e raio da foto. `<img>` que falha ao carregar: `alt` vazio no cartão; na página da oferta, `alt="Foto de <título>"`; se o arquivo faltar, o servidor já renderiza o placeholder (sem `onerror`, sem ícone quebrado).

### 2.13 Outros
- `.vazio` (estado vazio): ícone 40 px, `h2.t-2`, uma frase, uma ação (botão secundário).
- `.copiar-link` (página do vendedor): ver tela 3.4.
- `.menu-acoes` (área do vendedor): `<details>` com `<summary class="botao botao--secundario">Mais ações</summary>` e forms de ação (44 px cada). Sem JS funciona; com ou sem JS fecha ao sair do foco (melhoria opcional); `Esc` fecha (nativo em navegadores recentes).
- `.rodape`: "Pão de Cada Dia · Campus Paraíso · MG", "Pra sobreviver ao Cálculo.", links "Vender aqui", "Entrar"/"Sair", "Privacidade" (página a definir), nota "A ordem das ofertas muda todo dia, para todo mundo aparecer."

## 3. Telas

Breakpoints: base 375 px (funciona a partir de 320), `min-width:37.5em` (600), `min-width:60em` (960). Sem rolagem horizontal. Container 1120 px centrado em 1280.

### 3.1 Página inicial (`/?q=&cat=&hoje=&pagina=`)
Ordem (CA1): cabeçalho com identificação breve e `h1` + busca (2.2, 2.3) → chips de categoria (2.4) → "Disponíveis hoje" → `h2` da lista → lista de cartões → "Mostrar mais ofertas" → rodapé.
- `h2` da lista: "Ofertas" (padrão), "Disponíveis hoje" (filtro ativo) ou "Resultados para “bolo”" (busca). Sem contadores.
- 375 px: faixa azul ocupa ~200 px; o primeiro cartão aparece sem rolar em telas ≥ 640 px de altura. Uma coluna. 1280 px: faixa azul de largura total com conteúdo centrado; `h1` e busca na mesma faixa lado a lado (busca com 560 px); chips e filtro em uma linha; grade de 3 colunas.
- Paginação sem JS: cada página 20 cartões; "Mostrar mais ofertas" é link `?...&pagina=N+1`; o servidor renderiza as ofertas das páginas 1 até N (cumulativo), assim a âncora do cartão sempre existe ao voltar.
- Preservar contexto (CA2): todo link de cartão leva os parâmetros atuais (`q`, `cat`, `hoje`, `pagina`). Na oferta, "← Voltar para a lista" é um link para `/?<mesmos parâmetros>#oferta-<id>`; o botão Voltar do navegador também restaura a posição. O alvo da âncora recebe `scroll-margin-top:16px`.
- Estados: **vazio** (nenhuma oferta publicada): ícone, "Ainda não há ofertas por aqui", "Quando alguém publicar, aparece nesta lista.", botão "Quero vender" → `/cadastrar`. **Busca/filtro sem resultado**: "Nada encontrado para “<termo>”" + "Confira a escrita ou tente outra palavra." + botão secundário "Limpar filtros" (→ `/`); se só "Disponíveis hoje" estiver ativo e sem resultado: "Ninguém confirmou oferta para hoje ainda" + "Limpar filtros" + link "Ver todas as ofertas". **Erro de servidor**: página 500 (3.10). **Carregando**: renderização no servidor; não há esqueleto. Fotos preguiçosas mostram o fundo Névoa até chegar.

### 3.2 Página da oferta (`/oferta/<id>`)
Ordem do DOM: link "← Voltar para a lista" → `h1` (título) → selo → preço (com "A partir de" se houver variações) → retirada/entrega (ícone `pino` + texto; "Entrega" com `caminhao`) → fotos → descrição → bloco de alimento (2.11, se categoria for alimento) → variações + botão + aviso → vendedor → "Denunciar esta oferta".
- **Fotos**: primeira foto grande (4:3, raio 16, `fetchpriority="high"`, não preguiçosa), até 2 menores abaixo em grade de 2 (mobile) ou ao lado (desktop). Sem carrossel, sem lightbox. Sem foto: placeholder 2.12. `alt="Foto de <título>"` na 1ª; "Foto 2 de <título>" nas demais.
- **Variações** (CA1): `<form method="get" action="/oferta/<id>/whatsapp" target="_blank">` com `<fieldset><legend>Escolha uma opção <span class="opcional">(opcional)</span></legend>` e um rádio por variação em `.opcao` (nome + preço à direita, 56 px). Nada selecionado = mensagem só com o nome da oferta. Botão `type="submit"` "Consultar no WhatsApp" (primário, largura total no mobile, ícone `mensagem` genérico, não o logo do WhatsApp). O servidor registra o clique, monta a mensagem ("Oi! Vi “<título>”<, opção “<variação>”> no Pão de Cada Dia. Ainda está disponível?") e responde 302 para `wa.me`; assim o número não entra no HTML (CA6). Sem variações: o mesmo form só com o botão. Texto do botão avisa o destino: abaixo, `.legenda` "Abre em outra aba".
- Aviso 2.10 logo abaixo do botão.
- **Vendedor**: bloco com iniciais em círculo (Barlow Cond., Azul 50), nome (link para `/vendedor/<slug>`, `.texto-forte`), "Ver todas as ofertas de <nome>".
- **Contato não autorizado**: no lugar do botão, `.aviso--info`: "Este vendedor ainda não liberou o WhatsApp para contato por aqui." sem ação (e sem expor o número).
- **Esgotado / Vendido**: sem botão; mensagem: "Esta oferta está esgotada no momento." / "Esta oferta já foi vendida." + link "Ver outras ofertas de <nome>". Preço riscado no Vendido.
- Rodapé da página: "Denunciar esta oferta" (`.botao--link`, ícone `bandeira`) → `/oferta/<id>/denunciar`.
- 375: coluna única. 1280: duas colunas (fotos 55% | conteúdo 45%), conteúdo com título, selo, preço, retirada, descrição, variações+botão+aviso e vendedor; bloco de alimento abaixo das fotos, na coluna esquerda; coluna de conteúdo não "gruda".
- **Indisponível/removido** (pausado, oculto, vendedor excluído, inexistente, venda pontual vencida): resposta 404 com a tela 3.10 ("Esta oferta não está mais disponível"), sem revelar o motivo.

### 3.3 Denúncia (`/oferta/<id>/denunciar`)
`h1` "Denunciar oferta", resumo da oferta (título e vendedor) em `.legenda`. Formulário: `fieldset` "Qual é o problema?" com rádios (lista abaixo, obrigatório), campo "Conte mais (opcional)" (`textarea`, 500 caracteres, dica "Não coloque dados pessoais seus."), botão primário "Enviar denúncia", link "Cancelar" (volta para a oferta). Sem cadastro, sem pedir nome ou e-mail. Sucesso: página com `.aviso--sucesso` "Recebemos sua denúncia. Obrigado por avisar." e botão "Voltar para a oferta" (ou para o início se a oferta saiu do ar). Limite de tentativas: `.aviso--erro` "Você enviou muitas denúncias em pouco tempo. Tente de novo mais tarde." Estados: erro de validação (nenhum motivo): "Escolha o motivo da denúncia." junto ao grupo.

### 3.4 Página do vendedor (`/vendedor/<slug>`)
`h1` nome/marca; apresentação curta; `dl` com "Atende em" (região) e "Horários"; campos vazios simplesmente não aparecem. `.copiar-link`: caixa com o endereço completo da página em `<input readonly value="https://…/vendedor/ana" aria-label="Endereço da página">` (`user-select:all`) sempre visível + `.legenda` "Toque no endereço para selecionar e copie." Com JS: o script adiciona dois botões: "Copiar link" (clipboard; confirma com `role="status"` "Link copiado") e, se `navigator.share` existir, "Compartilhar". Sem JS, o campo selecionável é a alternativa (CA5). Depois: `h2` "Ofertas de <nome>" e a lista de cartões (2.5, sem paginação até 20). 
- Vazio: "<nome> não tem ofertas ativas agora." + link "Ver todas as ofertas". Vendedor inexistente/excluído: 404.
- 1280: cabeçalho do vendedor em duas colunas (nome e texto | região e horários); grade de 3 colunas.

### 3.5 Entrar / Cadastrar (`/entrar`, `/cadastrar`)
Coluna única de 28rem centrada em qualquer largura; sem cabeçalho de busca. Dois links cruzados ("Não tem conta? Cadastrar" / "Já tem conta? Entrar").
- **Entrar**: E-mail, Senha, botão "Entrar". Erro único e genérico: "E-mail ou senha incorretos. Confira e tente de novo." (não diz qual). Excesso de tentativas: "Muitas tentativas. Espere alguns minutos e tente de novo."
- **Cadastrar**: "Nome ou marca" (ex.: "Doces da Ana"), E-mail, Senha (dica "Mínimo de 8 caracteres." sem regras complicadas), "WhatsApp com DDD" (`inputmode="tel"`, ex.: "(35) 91234-5678", dica "Só você e a administração veem o número. Se você autorizar, quem tocar em “Consultar no WhatsApp” abre a conversa com você."), caixa "Mostrar meu WhatsApp para quem quer comprar (opcional)" **desmarcada**, com explicação "Sem isso, seus anúncios não aparecem na vitrine. Você pode mudar isso a qualquer momento no Perfil." Botão "Criar conta". Sucesso: segue direto para "Meus anúncios" com `.aviso--sucesso` "Conta criada. Agora é só adicionar seu primeiro anúncio."
- Sem JS: nada a mais. Mostrar/ocultar senha é melhoria opcional (botão "Mostrar senha" com `aria-pressed`).
- Recuperação de senha: ver Pendências.

### 3.6 Área do vendedor (`/meus-anuncios`)
Requer login. `h1` "Meus anúncios". Em primeiro lugar, ordem de foco e de leitura: botão **"Adicionar anúncio"** (primário, largura total no mobile, ícone `mais`, único botão sólido grande da tela) → mensagens → lista.
- Aviso quando houver anúncio "Aguardando aprovação": `.aviso--info` "Seu primeiro anúncio está em análise. Quando for aprovado, ele aparece para todo mundo."
- Item (`.anuncio`, `<article id="anuncio-<id>">`): miniatura 72 px, título (`.texto-forte`), selo (2.6, incluindo os só do vendedor), preço, linha `.legenda` com o tipo ("Oferta do dia", "Venda única", "Sempre na vitrine") e, quando relevante, "Confirmado até 23h59" / "Confirmado até 18:00" / "Última confirmação há 12 dias". Botões, na ordem: 
  1. "Confirmar disponível hoje" (`.botao--confirmar`, 1 clique; aparece em oferta do dia e também em oferta recorrente ("Sempre na vitrine") ainda não confirmada hoje: confirmar põe a oferta em "Disponível hoje" até 23h59; em venda pontual "Precisa de confirmação" o botão é "Confirmar que ainda vendo"; rótulos em `texts/seller.py::ACTION_LABELS`);
  2. "Editar" (secundário, link);
  3. `<details class="menu-acoes">` "Mais ações": "Pausar" ou "Reativar", "Marcar como esgotado" ou "Voltou ao estoque", "Marcar como vendido" ou "Voltar a vender". Cada um é botão POST de 44 px; nenhuma exige confirmação extra (todas reversíveis).
  Anúncio "Aguardando aprovação": só "Editar".
- Feedback (CA7): volta à lista com `.aviso--sucesso` e foco no `main` + âncora: "Pronto: “Bolo de pote” confirmado como disponível hoje." / "…pausado. Ele saiu da vitrine." / "…reativado." / "…marcado como esgotado." / "…marcado como vendido."
- Vazio: "Você ainda não tem anúncios" + "Anuncie o que você vende em poucos minutos." + botão "Adicionar anúncio" (o mesmo, sem duplicar).
- Erro: falha ao salvar ação → `.aviso--erro` "Não conseguimos salvar. Tente de novo." sem perder a página.
- 1280: lista em coluna única de largura 48rem centrada com ações em linha ao lado do título; sem tabela.

### 3.7 Formulário de anúncio (`/meus-anuncios/novo`, `.../<id>/editar`)
`h1` "Novo anúncio" / "Editar anúncio". Coluna única de 40rem. Botões no fim: "Salvar e publicar" (novo) / "Salvar alterações" (edição) e link-botão "Cancelar". **Sem rascunho**: o preenchimento é preservado em caso de erro (CA8); fotos já enviadas continuam e as novas precisam ser escolhidas de novo, com aviso.

**Decisão sem JS: todas as seções ficam no HTML, e cada seção condicional é um `<fieldset>` com legenda e instrução ("Preencha só se …").** Com JS, o script esconde as seções que não valem para o tipo/categoria escolhidos e as mostra de novo ao mudar (melhoria progressiva; `hidden` aplicado pelo script, nunca pelo servidor no primeiro render). Sem JS nada some, nada fica inacessível, e o servidor ignora campos que não valem para o tipo. Alternativa descartada: `<details>` (esconde campo obrigatório, ruim para quem tem pressa) e botão "Atualizar formulário" (passo extra).

Ordem dos campos:
1. **Tipo** (`fieldset`, rádios em `.opcao`, obrigatório): "Faço sempre (ou por encomenda)" `recorrente`; "Tenho hoje" `do dia`; "Venda única" `pontual`. Cada opção com `.legenda`: "Fica na vitrine até você pausar." / "Só aparece em “Disponíveis hoje” depois que você confirma. Vale até 23h59 do dia." / "Fica até você marcar como vendido. Pedimos para você confirmar a cada 14 dias."
2. **Título** (ex.: "Bolo de pote de ninho com morango").
3. **Categoria** (select; opções vindas do banco).
4. **Preço** em R$ (ex.: "8,50"; `inputmode="decimal"`, aceita vírgula; sem máscara de JS). Com variações preenchidas, o preço vira "A partir de" o menor valor; rótulo "Preço (ou o menor preço)".
5. **Descrição curta (opcional)** (ex.: "Feito no dia. Dá pra pedir sem leite.") 300 caracteres.
6. **Retirada ou entrega** (ex.: "Retirada no bloco 3, no intervalo das 10h") 100 caracteres: alimenta o resumo do cartão.
7. **Opções com preços diferentes (opcional)** (`fieldset`): 5 linhas fixas "Nome da opção" (ex.: "Ninho com morango") + "Preço" (ex.: "8,00"); linha vazia é ignorada; dica "Deixe em branco o que não usar."
8. **Fotos (opcional)**: `<input type="file" accept="image/jpeg,image/png,image/webp" multiple>`, dica "Até 3 fotos, cada uma de até 5 MB (JPG, PNG ou WebP)."; na edição, cada foto atual aparece em miniatura com caixa "Remover esta foto". Texto alternativo é o título.
9. **Só para oferta do dia** (`fieldset` com legenda "Só para oferta do dia"): "Horário de encerramento (opcional)" (`type="time"`, dica "Se deixar em branco, vale até 23h59.") e caixa "Já confirmar como disponível hoje" (marcada por padrão).
10. **Só para comidas e doces** (`fieldset`): "Porção" (ex.: "1 pote de 200 g"), "Ingredientes" (ex.: "Leite, ninho, morango, açúcar."), "Alergênicos" (ex.: "Contém leite. Pode conter traços de amendoim."); todos opcionais, com dica comum "Se você não preencher, a página mostra “Não informado pelo vendedor”. Escreva só o que você tem certeza."
11. Botões.
- Estados: erro por campo (2.8) e resumo no topo; erro de upload ("Esta foto passou de 5 MB. Escolha uma menor." / "Este arquivo não é uma foto válida."); envio lento: texto "Enviando fotos, pode demorar um pouco…" abaixo dos botões quando o formulário é enviado (JS), caso contrário o navegador mostra o progresso. Sucesso novo: "Anúncio enviado para análise. Ele aparece para todo mundo quando a equipe aprovar." (primeiro anúncio) ou "Anúncio publicado." Edição: "Alterações salvas."
- Acesso a anúncio de outro vendedor: 404 (3.10).
- 1280: mesma coluna de 40rem centrada; fotos e opções em grade de 2 colunas.

### 3.8 Perfil do vendedor (`/perfil`)
`h1` "Perfil". Seções (`h2.t-2`) em coluna única de 40rem:
1. "Seus dados": Nome ou marca; "Apresentação (opcional)" (ex.: "Cookies e brownies feitos em casa, sábado entrego no campus."); "Onde você atende (opcional)" (ex.: "Campus Paraíso, blocos 1 a 3"); "Horários (opcional)" (ex.: "Seg a sex, intervalo das 10h"). Link da página pública (somente leitura) com `.copiar-link`.
2. "WhatsApp": campo "WhatsApp com DDD"; rádios `fieldset` "Mostrar o número para quem quer comprar?": "Sim, mostrar. O botão “Consultar no WhatsApp” fica ativo nos meus anúncios." / "Não. Meus anúncios ficam sem botão de contato." Texto de apoio: "Você pode mudar isso quando quiser. Se mudar para “Não”, o contato some na hora." Estado atual sempre visível ao lado do título ("Contato liberado" com ícone check / "Contato não liberado" com ícone `circulo-menos`).
3. "Segurança": e-mail (somente leitura) e link "Trocar senha" (ver Pendências).
4. Botão "Salvar alterações" ao fim das seções 1 a 2 (um só form).
5. Zona de exclusão (`h2` "Excluir conta", separada por linha, `.aviso--atencao` descritivo): "Ao excluir, seus anúncios saem da vitrine na hora e isso não pode ser desfeito." Ação discreta: link "Excluir minha conta…" (`.botao--link`) → página `/perfil/excluir-conta` (sem JS, sem modal).
- **Confirmação de exclusão**: `h1` "Excluir sua conta?", lista do que acontece (anúncios, página do vendedor e contato somem na hora), campo "Digite sua senha para confirmar", botão `.botao--perigo` "Excluir minha conta para sempre" e botão secundário "Voltar, não excluir" (primeiro na ordem do DOM e do foco, foco inicial **não** automático no perigo). Sucesso: vai ao início com `.aviso--sucesso` "Sua conta foi excluída. Seus anúncios saíram da vitrine."

### 3.9 Administração mínima (`/admin`)
Só administrador; mesma casca do site. `nav aria-label="Administração"` com links (aba ativa `aria-current="page"` + sublinhado, não só cor): Aprovações, Denúncias, Anúncios, Categorias. Sem gráficos, sem totais decorativos. Mobile: cartões empilhados; ≥ 960: tabela `<table>` com `<caption>` visualmente oculta, `scope="col"`, linhas de 56 px, ações na última coluna.
- **Aprovações**: lista de anúncios "Aguardando aprovação": miniatura, título, vendedor, categoria, preço, data; link "Ver como visitante" (pré-visualização só do admin); botões "Aprovar" (`.botao--confirmar`) e "Ocultar" (secundário). Vazio: "Nada esperando aprovação."
- **Denúncias**: abertas primeiro; cada item com motivo, texto do visitante (escapado, até 500 caracteres), data, link para a oferta, selo "Aberta"/"Tratada"; ações "Ocultar anúncio" (perigo suave: secundário) e "Marcar como tratada". Vazio: "Nenhuma denúncia aberta."
- **Anúncios**: busca por título ou vendedor (mesmo componente de busca) e lista com selo e botão "Ocultar" / "Mostrar de novo". Oculto mostra selo "Oculto pela administração" (só admin).
- **Categorias**: lista com campo de nome, campo numérico "Posição" (ordem), e botões "Salvar", "Esconder"/"Mostrar"; formulário "Nova categoria" (ex.: "Livros e apostilas"). Sem excluir no MVP.
- Feedback com `.aviso` no topo (2.9). Confirmação extra apenas para "Ocultar" em massa (não há ação em massa no MVP).

### 3.10 Páginas de erro e estados globais
Layout central, `h1` + 1 frase + 1 ação + (opcional) `.legenda` com código. Sem humor forçado, sem ilustração pesada (ícone 48 px).
- **404 / oferta indisponível ou removida**: "Esta oferta não está mais disponível" / "Ela pode ter sido vendida, pausada ou removida." / botão "Ver outras ofertas". Para URL que não existe: "Não encontramos esta página" / "O endereço pode estar errado." / "Ir para o início".
- **403** (ação não permitida; na prática vira 404 para recursos de outro vendedor).
- **500/503**: "Algo deu errado do nosso lado" / "Já estamos de olho. Tente de novo em instantes." / botão "Tentar de novo" (link para a mesma URL). HTML estático com CSS inline mínimo e sem fonte externa, para funcionar mesmo com o app falhando.
- **Sem conexão**: o navegador mostra a própria tela; o app não consegue renderizar nada. Sem service worker no MVP. Em envio de formulário falho por rede o navegador preserva o histórico; nenhuma promessa de offline.
- **Limite de tentativas** (429): "Muitas tentativas" / "Espere alguns minutos e tente de novo."
- **Carregando**: sem estado dedicado (páginas renderizadas no servidor). Para envio de formulário: 2.7 e 3.7.

## 4. Navegação por teclado e acessibilidade

- Ordem de foco = ordem do DOM = ordem visual (sem `tabindex` positivo). Início: pular → logo → link do cabeçalho → busca → botão Buscar → chips → "Disponíveis hoje" → cartões (um foco por cartão) → "Mostrar mais ofertas" → rodapé. Oferta: pular → logo → cabeçalho → voltar → (fotos não focáveis) → rádios de variação → botão → link do vendedor → Denunciar. Menus `<details>`: Enter/Espaço abrem; `Tab` percorre as ações.
- Skip link "Pular para o conteúdo" em toda página; `main` com `tabindex="-1"` recebe o foco quando há mensagem ou erro (JS opcional chama `main.focus()`; sem JS, o título "Erro: …" e o aviso no topo do `main` bastam).
- Foco sempre visível (tokens), contraste do foco ≥ 3:1. Alvos ≥ 44×44 (chips, botões, links de cabeçalho, linhas de rádio, `summary`); links no meio de texto corrido têm sublinhado e `padding` vertical para a área de toque ou ficam em linha própria.
- Semântica: `header`, `nav` com `aria-label`, `main`, `footer`; `h1`→`h2` sem pular nível; listas reais (`ul`) para chips e cartões; `article` por oferta; `dl` para dados; `table` só na administração; `fieldset/legend` para grupos de rádio. ARIA só quando o nativo não resolve (`aria-current`, `aria-invalid`, `aria-describedby`, `role=status|alert`, `role=search`).
- Status nunca só por cor (2.6). Preço riscado em Vendido vem junto do texto "Vendido". Zoom até 200% e fontes grandes sem perda de conteúdo; layout em `rem` e `minmax`, sem alturas fixas em texto.
- Idioma `lang="pt-BR"`; `<title>` único por tela; erros de formulário ligados a campos com `aria-describedby`.
- Reduzir movimento respeitado (sem animação relevante). Sem pop-up, sem foco roubado, sem timeouts.
- Desempenho (conexão ruim): CSS único (~15 KB), sem framework de UI, fotos em dois tamanhos com `srcset`/`sizes` (cartão ~112 e ~400 px; oferta ~800 px), `width`/`height` sempre, lazy a partir do 3º cartão, 6 fontes subsetadas com preload só das 2 críticas.

## 5. Textos da interface (pt-BR, copiar para o arquivo de textos do projeto)

| Chave | Texto |
|---|---|
| marca.nome | Pão de Cada Dia |
| marca.assinatura | Compra e venda entre estudantes |
| marca.comunidade | Campus Paraíso · MG |
| marca.slogan | Pra sobreviver ao Cálculo. |
| pular | Pular para o conteúdo |
| cabecalho.vender | Vender aqui |
| cabecalho.meus_anuncios | Meus anúncios |
| cabecalho.admin | Administração |
| inicio.titulo | O que tem no campus hoje? |
| busca.rotulo (oculto) | Buscar produto, serviço ou vendedor |
| busca.placeholder | Bolo, apostila, aula particular… |
| busca.botao | Buscar |
| categorias.todas | Tudo |
| filtro.hoje | Disponíveis hoje |
| lista.titulo | Ofertas |
| lista.titulo_busca | Resultados para “{termo}” |
| lista.mais | Mostrar mais ofertas |
| cartao.ver | Ver oferta |
| cartao.a_partir_de | A partir de |
| vazio.lista.titulo | Ainda não há ofertas por aqui |
| vazio.lista.texto | Quando alguém publicar, aparece nesta lista. |
| vazio.lista.acao | Quero vender |
| semresultado.titulo | Nada encontrado para “{termo}” |
| semresultado.texto | Confira a escrita ou tente outra palavra. |
| semresultado.hoje.titulo | Ninguém confirmou oferta para hoje ainda |
| semresultado.hoje.texto | Veja todas as ofertas ou volte mais tarde. |
| semresultado.limpar | Limpar filtros |
| selo.disponivel_hoje | Disponível hoje |
| selo.sob_encomenda | Sob encomenda |
| selo.esgotado | Esgotado |
| selo.vendido | Vendido |
| selo.pausado | Pausado |
| selo.precisa_confirmacao | Precisa de confirmação |
| selo.aguardando_aprovacao | Aguardando aprovação |
| selo.oculto | Oculto pela administração |
| oferta.voltar | Voltar para a lista |
| oferta.variacoes | Escolha uma opção |
| oferta.whatsapp | Consultar no WhatsApp |
| oferta.whatsapp_dica | Abre em outra aba |
| oferta.aviso | Abrir o WhatsApp não é um pedido confirmado. Disponibilidade, pagamento e entrega são combinados direto com quem vende. |
| oferta.mensagem_whatsapp | Oi! Vi “{titulo}”{, opção “{variacao}”} no Pão de Cada Dia. Ainda está disponível? |
| oferta.sem_contato | Este vendedor ainda não liberou o WhatsApp para contato por aqui. |
| oferta.esgotada | Esta oferta está esgotada no momento. |
| oferta.vendida | Esta oferta já foi vendida. |
| oferta.outras_do_vendedor | Ver outras ofertas de {nome} |
| oferta.vendedor | Vendido por |
| oferta.retirada | Retirada ou entrega |
| oferta.denunciar | Denunciar esta oferta |
| oferta.sem_foto | Sem foto |
| alimento.titulo | Sobre este alimento |
| alimento.porcao | Porção |
| alimento.ingredientes | Ingredientes |
| alimento.alergenicos | Alergênicos |
| alimento.nao_informado | Não informado pelo vendedor |
| alimento.nota | Informado por quem vende. Confirme com a pessoa se tiver alergia. |
| vendedor.atende | Atende em |
| vendedor.horarios | Horários |
| vendedor.ofertas | Ofertas de {nome} |
| vendedor.vazio | {nome} não tem ofertas ativas agora. |
| vendedor.link_dica | Toque no endereço para selecionar e copie. |
| vendedor.copiar | Copiar link |
| vendedor.compartilhar | Compartilhar |
| vendedor.copiado | Link copiado |
| denuncia.titulo | Denunciar oferta |
| denuncia.pergunta | Qual é o problema? |
| denuncia.motivo.golpe | Parece golpe ou fraude |
| denuncia.motivo.proibido | Produto ou serviço proibido ou perigoso |
| denuncia.motivo.ofensivo | Conteúdo ofensivo ou impróprio |
| denuncia.motivo.errado | Informação errada ou desatualizada |
| denuncia.motivo.repetido | Anúncio repetido |
| denuncia.motivo.outro | Outro motivo |
| denuncia.texto | Conte mais (opcional) |
| denuncia.texto_dica | Não coloque dados pessoais seus. |
| denuncia.enviar | Enviar denúncia |
| denuncia.ok | Recebemos sua denúncia. Obrigado por avisar. |
| denuncia.erro_motivo | Escolha o motivo da denúncia. |
| denuncia.limite | Você enviou muitas denúncias em pouco tempo. Tente de novo mais tarde. |
| entrar.titulo | Entrar |
| entrar.botao | Entrar |
| entrar.erro | E-mail ou senha incorretos. Confira e tente de novo. |
| entrar.limite | Muitas tentativas. Espere alguns minutos e tente de novo. |
| entrar.sem_conta | Não tem conta? Cadastrar |
| cadastrar.titulo | Criar conta de vendedor |
| cadastrar.botao | Criar conta |
| cadastrar.ja_tem | Já tem conta? Entrar |
| cadastrar.ok | Conta criada. Agora é só adicionar seu primeiro anúncio. |
| campo.email | E-mail |
| campo.senha | Senha |
| campo.senha_dica | Mínimo de 8 caracteres. |
| campo.nome_marca | Nome ou marca |
| campo.nome_marca_ex | Exemplo: Doces da Ana |
| campo.whatsapp | WhatsApp com DDD |
| campo.whatsapp_ex | Exemplo: (35) 91234-5678 |
| campo.whatsapp_dica | Só você e a administração veem o número. Se você autorizar, quem tocar em “Consultar no WhatsApp” abre a conversa com você. |
| campo.mostrar_whatsapp | Mostrar meu WhatsApp para quem quer comprar |
| campo.opcional | (opcional) |
| form.obrigatorios | Campos sem “(opcional)” são obrigatórios. |
| meus.titulo | Meus anúncios |
| meus.adicionar | Adicionar anúncio |
| meus.vazio.titulo | Você ainda não tem anúncios |
| meus.vazio.texto | Anuncie o que você vende em poucos minutos. |
| meus.em_analise | Seu primeiro anúncio está em análise. Quando for aprovado, ele aparece para todo mundo. |
| meus.editar | Editar |
| meus.mais | Mais ações |
| meus.confirmar_hoje | Confirmar disponível hoje |
| meus.confirmar_ainda | Confirmar que ainda vendo |
| meus.pausar | Pausar |
| meus.reativar | Reativar |
| meus.esgotado | Marcar como esgotado |
| meus.voltou_estoque | Voltou ao estoque |
| meus.vendido | Marcar como vendido |
| meus.voltar_vender | Voltar a vender |
| meus.ok.confirmado | Pronto: “{titulo}” confirmado como disponível hoje. |
| meus.ok.pausado | “{titulo}” pausado. Ele saiu da vitrine. |
| meus.ok.reativado | “{titulo}” reativado. |
| meus.ok.esgotado | “{titulo}” marcado como esgotado. |
| meus.ok.vendido | “{titulo}” marcado como vendido. |
| meus.erro | Não conseguimos salvar. Tente de novo. |
| meus.tipo.recorrente | Sempre no catálogo |
| meus.tipo.dia | Oferta do dia |
| meus.tipo.pontual | Venda única |
| meus.confirmado_ate | Confirmado até {hora} |
| meus.ultima_confirmacao | Última confirmação há {n} dias |
| anuncio.novo | Novo anúncio |
| anuncio.editar | Editar anúncio |
| anuncio.tipo | O que você vai anunciar? |
| anuncio.tipo.recorrente | Faço sempre (ou por encomenda) |
| anuncio.tipo.recorrente_dica | Fica na vitrine até você pausar. |
| anuncio.tipo.dia | Tenho hoje |
| anuncio.tipo.dia_dica | Só aparece em “Disponíveis hoje” depois que você confirma. Vale até 23h59 do dia. |
| anuncio.tipo.pontual | Venda única |
| anuncio.tipo.pontual_dica | Fica até você marcar como vendido. Pedimos para você confirmar a cada 14 dias. |
| anuncio.titulo | Título |
| anuncio.titulo_ex | Exemplo: Bolo de pote de ninho com morango |
| anuncio.categoria | Categoria |
| anuncio.preco | Preço (ou o menor preço), em R$ |
| anuncio.preco_ex | Exemplo: 8,50 |
| anuncio.descricao | Descrição curta |
| anuncio.descricao_ex | Exemplo: Feito no dia. Dá pra pedir sem leite. |
| anuncio.retirada | Retirada ou entrega |
| anuncio.retirada_ex | Exemplo: Retirada no bloco 3, no intervalo das 10h |
| anuncio.opcoes | Opções com preços diferentes |
| anuncio.opcoes_dica | Deixe em branco o que não usar. |
| anuncio.opcao_nome | Nome da opção |
| anuncio.opcao_nome_ex | Exemplo: Ninho com morango |
| anuncio.opcao_preco | Preço da opção |
| anuncio.fotos | Fotos |
| anuncio.fotos_dica | Até 3 fotos, cada uma de até 5 MB (JPG, PNG ou WebP). |
| anuncio.fotos_reenviar | Se o formulário voltar com erro, escolha as fotos de novo. |
| anuncio.foto_remover | Remover esta foto |
| anuncio.so_dia | Só para oferta do dia |
| anuncio.so_dia_instrucao | Preencha só se você escolheu “Tenho hoje”. |
| anuncio.encerramento | Horário de encerramento |
| anuncio.encerramento_dica | Se deixar em branco, vale até 23h59. |
| anuncio.ja_confirmar | Já confirmar como disponível hoje |
| anuncio.so_comida | Só para comidas e doces |
| anuncio.so_comida_instrucao | Preencha só se a categoria for “Comidas e doces”. |
| anuncio.porcao_ex | Exemplo: 1 pote de 200 g |
| anuncio.ingredientes_ex | Exemplo: Leite, ninho, morango, açúcar. |
| anuncio.alergenicos_ex | Exemplo: Contém leite. Pode conter traços de amendoim. |
| anuncio.comida_dica | Se você não preencher, a página mostra “Não informado pelo vendedor”. Escreva só o que você tem certeza. |
| anuncio.publicar | Salvar e publicar |
| anuncio.salvar | Salvar alterações |
| anuncio.cancelar | Cancelar |
| anuncio.enviando | Enviando fotos, pode demorar um pouco… |
| anuncio.ok.analise | Anúncio enviado para análise. Ele aparece para todo mundo quando a equipe aprovar. |
| anuncio.ok.publicado | Anúncio publicado. |
| anuncio.ok.salvo | Alterações salvas. |
| anuncio.erro.resumo | Corrija {n} campo(s) para continuar. |
| erro.obrigatorio | Preencha este campo. |
| erro.email | Digite um e-mail válido. Exemplo: ana@email.com |
| erro.senha_curta | A senha precisa ter pelo menos 8 caracteres. |
| erro.whatsapp | Digite um WhatsApp válido com DDD. Exemplo: (35) 91234-5678 |
| erro.preco | Digite um valor em reais. Exemplo: 8,50 |
| erro.horario | Digite um horário válido. Exemplo: 18:00 |
| erro.foto_grande | Esta foto passou de 5 MB. Escolha uma menor. |
| erro.foto_invalida | Este arquivo não é uma foto válida. Use JPG, PNG ou WebP. |
| erro.fotos_demais | Você pode enviar até 3 fotos. |
| erro.email_usado | Já existe uma conta com este e-mail. Tente entrar. |
| perfil.titulo | Perfil |
| perfil.dados | Seus dados |
| perfil.apresentacao_ex | Exemplo: Cookies e brownies feitos em casa. Sábado entrego no campus. |
| perfil.regiao | Onde você atende |
| perfil.regiao_ex | Exemplo: Campus Paraíso, blocos 1 a 3 |
| perfil.horarios | Horários |
| perfil.horarios_ex | Exemplo: Seg a sex, no intervalo das 10h |
| perfil.link_pagina | Endereço da sua página |
| perfil.whatsapp_titulo | WhatsApp |
| perfil.mostrar | Mostrar o número para quem quer comprar? |
| perfil.mostrar_sim | Sim, mostrar. O botão “Consultar no WhatsApp” fica ativo nos meus anúncios. |
| perfil.mostrar_nao | Não. Meus anúncios ficam sem botão de contato. |
| perfil.mostrar_apoio | Você pode mudar isso quando quiser. Se mudar para “Não”, o contato some na hora. |
| perfil.contato_liberado | Contato liberado |
| perfil.contato_nao | Contato não liberado |
| perfil.salvar | Salvar alterações |
| perfil.ok | Perfil atualizado. |
| perfil.excluir_titulo | Excluir conta |
| perfil.excluir_aviso | Ao excluir, seus anúncios saem da vitrine na hora e isso não pode ser desfeito. |
| perfil.excluir_link | Excluir minha conta… |
| excluir.titulo | Excluir sua conta? |
| excluir.lista | Seus anúncios saem da vitrine agora. Sua página de vendedor deixa de existir. Seu contato deixa de aparecer. Não dá para desfazer. |
| excluir.senha | Digite sua senha para confirmar |
| excluir.confirmar | Excluir minha conta para sempre |
| excluir.voltar | Voltar, não excluir |
| excluir.ok | Sua conta foi excluída. Seus anúncios saíram da vitrine. |
| excluir.senha_errada | Senha incorreta. Confira e tente de novo. |
| admin.titulo | Administração |
| admin.abas | Aprovações · Denúncias · Anúncios · Categorias |
| admin.aprovar | Aprovar |
| admin.ocultar | Ocultar |
| admin.mostrar | Mostrar de novo |
| admin.ver_visitante | Ver como visitante |
| admin.vazio_aprovacao | Nada esperando aprovação. |
| admin.vazio_denuncias | Nenhuma denúncia aberta. |
| admin.denuncia.aberta | Aberta |
| admin.denuncia.tratada | Tratada |
| admin.denuncia.tratar | Marcar como tratada |
| admin.denuncia.ocultar | Ocultar anúncio |
| admin.cat.nova | Nova categoria |
| admin.cat.nome_ex | Exemplo: Livros e apostilas |
| admin.cat.posicao | Posição |
| admin.cat.esconder | Esconder |
| admin.cat.mostrar | Mostrar |
| admin.cat.salvar | Salvar |
| admin.ok | Pronto. Alteração salva. |
| erro404.titulo | Não encontramos esta página |
| erro404.texto | O endereço pode estar errado. |
| erro404.acao | Ir para o início |
| indisponivel.titulo | Esta oferta não está mais disponível |
| indisponivel.texto | Ela pode ter sido vendida, pausada ou removida. |
| indisponivel.acao | Ver outras ofertas |
| erro500.titulo | Algo deu errado do nosso lado |
| erro500.texto | Já estamos de olho. Tente de novo em instantes. |
| erro500.acao | Tentar de novo |
| erro429.titulo | Muitas tentativas |
| erro429.texto | Espere alguns minutos e tente de novo. |
| rodape.ordem | A ordem das ofertas muda todo dia, para todo mundo aparecer. |
| rodape.privacidade | Privacidade |
| rodape.sair | Sair |
| salvando | Salvando… |

Proibido em qualquer texto: "corra", "últimas unidades" gerado pelo sistema, "mais vendidos", "popular", contadores de visitas ou de pessoas vendo, "garantido", "reservado".

## 6. Ícones

SVG inline, viewBox 24×24, `fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"`, `aria-hidden="true"`. Sugestão: desenhar à mão (são formas simples) em um único arquivo de sprite `static/icones.svg` com `<symbol id="i-…">`, usado por `<use href="…#i-nome">`; ou o conjunto livre Lucide (licença ISC) copiando só estes ícones, **sem instalar o pacote** (precisa de aprovação do dono se for usar). Sem WhatsApp oficial.

| id | Descrição | Uso |
|---|---|---|
| `lupa` | círculo + cabo diagonal | busca |
| `circulo-check` | círculo com check | selo Disponível hoje, sucesso, contato liberado |
| `relogio` | círculo com ponteiros | selo Sob encomenda |
| `circulo-menos` | círculo com traço horizontal | selo Esgotado, contato não liberado |
| `etiqueta-check` | etiqueta de preço com check | selo Vendido |
| `pausa` | dois traços verticais | selo Pausado |
| `alerta-circulo` | círculo com ! | Precisa de confirmação, erro |
| `ampulheta` | ampulheta | Aguardando aprovação |
| `alerta-triangulo` | triângulo com ! | erro de campo, atenção |
| `info` | círculo com i | informação, aviso do WhatsApp |
| `mensagem` | balão de fala simples com três pontos opcionais (genérico) | botão Consultar no WhatsApp |
| `imagem` | quadro com montanha e sol | placeholder de foto |
| `pino` | pino de mapa | retirada |
| `caminhao` | caminhão simples | entrega |
| `check` | check | chip ativo |
| `mais` | cruz | Adicionar anúncio |
| `lapis` | lápis | Editar |
| `seta-direita` | seta | "Ver oferta" |
| `seta-esquerda` | seta | Voltar para a lista |
| `copiar` | dois quadrados sobrepostos | Copiar link |
| `compartilhar` | três pontos ligados | Compartilhar |
| `bandeira` | bandeira | Denunciar |
| `sol` | sol | filtro Disponíveis hoje |
| `usuario` | busto | vendedor / perfil |
| `x` | X | fechar, remover foto |

## Componentes (resumo)

| Componente | Existente ou novo | Onde fica |
|---|---|---|
| Tokens, fontes, base | novo | `static/css/app.css` (seção tokens), `static/fontes/` |
| Casca, pular, cabeçalho, logo, rodapé | novo | layout base + parcial do cabeçalho |
| Busca, chips, filtro hoje | novo | parcial `filtros` |
| Cartão de oferta, selo, placeholder de foto | novo | parciais `cartao-oferta`, `selo`, `foto` |
| Botões, campos, aviso, `.vazio`, menu de ações | novo | CSS de componentes + parciais de formulário |
| Bloco de alimento, copiar link, aviso de contato | novo | parciais da oferta e do vendedor |
| Sprite de ícones | novo | `static/icones.svg` |

## O que o dev precisa implementar

1. Tokens, `@font-face` com `font-display:swap` e CSS único conforme as seções 1 e 2; sprite de ícones; logo SVG e favicon.
2. Todas as telas da seção 3, com HTML semântico, estados (vazio, sem resultado, erro, 404/500/429) e textos da seção 5 em um único arquivo de textos.
3. Parâmetros preservados em todos os links da lista (`q`, `cat`, `hoje`, `pagina`), âncora `#oferta-<id>` e paginação cumulativa.
4. `GET /oferta/<id>/whatsapp?variacao=<id>`: registra o clique, monta a mensagem (texto na tabela) e redireciona 302 para `wa.me`. Responde 404 se o contato não estiver autorizado.
5. Melhorias progressivas de JS (todas opcionais e pequenas): copiar/compartilhar link; esconder seções condicionais do formulário; texto "Salvando…"; foco no `main` após mensagem; mostrar senha.
6. Redirecionar após ações do vendedor com mensagem e âncora `#anuncio-<id>`; CSRF em todo `<form method="post">`.
7. Imagens: `srcset`/`sizes`, `width`/`height` e `loading` conforme 2.5/3.2.

## Arquivos de apresentação afetados

Projeto vazio: tudo é novo. Previstos (nomes sujeitos à stack): `static/css/app.css`, `static/fontes/*.woff2` e `OFL.txt`, `static/icones.svg`, `static/logo.svg`, `static/favicon.*`, templates (layout, parciais, uma por tela), arquivo de textos pt-BR. O designer não toca em rotas, validação, banco nem regra de expiração.

## Pendências para o dev

- Obter os woff2 (Google Fonts, OFL) e subsetar; confirmar tamanho total (alvo ≤ 120 KB para as 6).
- Regra de estado (público) e ordem do rodízio ficam no servidor; a UI só recebe o estado final: `disponivel_hoje | sob_encomenda | esgotado | vendido | nenhum`, e os de vendedor `pausado | precisa_confirmacao | aguardando_aprovacao`.
- Redirecionador de WhatsApp (item 4 acima) conta o clique agregado (CA16) sem IP nem cookie.
- Limites de tentativas e mensagens de 429 em login, denúncia e upload; CSRF nos formulários.
- Recuperação de senha: se sair do MVP, não mostrar link morto; mostrar `.legenda` "Esqueceu a senha? Fale com a administração em <contato a definir>."
- Página "Privacidade" mínima (link no rodapé) e texto da LGPD sobre o WhatsApp: precisa de conteúdo do dono/produto.
- Pré-visualização de anúncio pendente para o admin e filtro de dados "(exemplo)" nos dados de demonstração (selo textual "(exemplo)" no título).
- Verificar contraste real do tema no navegador com as fontes reais e capturas em 375 e 1280 (esta spec não foi verificada visualmente: projeto vazio, sem servidor).

## Decisões e suposições

1. **Cartão sem botão secundário.** Justificativa em 2.5; o cartão inteiro é um único link com "Ver oferta" como sinal de ação.
2. **Cartão horizontal no celular, vertical e em grade no desktop.** O lead pediu foto como principal elemento visual; a lista de 112 px segue a página 5 do PDF e mantém várias ofertas por tela em conexão lenta.
3. **Filtros por links `<a>` (não rádios/checkbox)**: funcionam sem JS, mantêm a busca e produzem URLs compartilháveis.
4. **Campo e chip com borda `#7B8499`, não Névoa**: Névoa sobre Branco tem ~1,2:1 e falharia o critério de 3:1 para componentes (WCAG 1.4.11). Névoa continua em linhas de cartão e fundos. Desvio pequeno da identidade, justificado por CA20.
5. **Foco por contorno de 3 px** com o halo Azul 50 só decorativo (Azul 50 sobre Papel não atinge 3:1).
6. **Título h1 de 32/36 no celular** (a identidade dá 40/44) para não quebrar "O que tem no campus hoje?" em 3 linhas.
7. **Preço em Vendido e Esgotado em Grafite**; verde só para oferta ainda disponível; Esgotado continua sem preço riscado.
8. **Contato por redirecionamento servidor** (`/oferta/<id>/whatsapp`) em vez de `href` direto: mantém o número fora do HTML (CA6), registra o clique (CA16) e a variação escolhida entra na mensagem sem JS.
9. **Formulário com seções sempre no HTML** e JS só para esconder; escolha em 3.7.
10. **Sem rascunho**; preservar preenchimento. Arquivos de foto não são preservados após erro (limitação do navegador) e isso é dito na tela.
11. **Sem confirmação extra nas ações de estado** (pausar, esgotado, vendido): todas são reversíveis no mesmo menu. Só exclusão de conta pede confirmação (página própria com senha).
12. **Sem barra de abas inferior** (Vitrine, Conversas, Vender, Perfil da maquete): sem chat, a navegação cabe em um link no cabeçalho + rodapé; reduz alvos e ruído.
13. **Sem "Excluir anúncio" no MVP**: pausar já tira da exposição; excluir a conta remove tudo. Pode entrar depois.
14. **Sem banner, sem "mais pedidos", sem "Reservado", sem "NOVO HOJE", sem modo noturno, sem contadores.** O rodapé explica o rodízio diário.
15. Administração: aprovar ou ocultar; sem campo de motivo ao vendedor no MVP.
16. Página do vendedor não tem botão de WhatsApp próprio; o contato fica na oferta, onde há mensagem e aviso.
17. Se o vendedor não autorizou o WhatsApp, o anúncio publica sem botão de contato e com o aviso da tela 3.2. Isso é consequência do CA6 e deve ser confirmado com o dono.

## Perguntas em aberto

- Sem autorização do número, o anúncio pode ser publicado (como na decisão 17) ou o vendedor deve ser impedido de publicar? Sugestão: permitir, com alerta no formulário "Sem liberar o WhatsApp, ninguém consegue falar com você por aqui."
- Tamanho máximo de foto: assumido 5 MB; o `arquiteto`/`dev` confirmam.
- Domínio e endereço final do link da página do vendedor (para o exemplo e o campo copiar).
