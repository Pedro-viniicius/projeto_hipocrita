# Brief — Vitrine "Pão de Cada Dia" (MVP)

Origem: pedido do dono em 2026-11-05, transcrito abaixo sem alterações (seções 1 a 10), seguido do adendo do lead com a identidade visual e os critérios de aceite numerados.

**Autorização do dono:** o pedido manda apresentar o plano e implementar **sem esperar aprovação**. Os quatro itens "[confirme]" foram confirmados pelo dono em 2026-11-05 com os valores sugeridos (ver `docs/produto/decisoes.md`).

---

# Papel e modo de trabalho

Projete e implemente, de ponta a ponta, uma plataforma web gratuita para divulgar produtos e serviços vendidos por pessoas de uma comunidade universitária. Quero um produto leve, simples, discreto e funcional: baixa carga cognitiva, fácil de manter e fácil de iniciar uma compra. Não quero apenas um layout bonito. Implemente os fluxos essenciais com persistência real dos dados.

Modo de trabalho:
- Planeje brevemente e depois execute até entregar algo funcionando. Não pare no planejamento.
- Não me faça perguntas que possam ser resolvidas com uma suposição razoável. Decida, siga em frente e registre cada suposição em uma seção "Decisões e suposições" na entrega final.
- Se houver um repositório existente, examine a estrutura e siga as convenções dele antes de qualquer outra coisa.
- Se precisar cortar escopo por limite de tempo ou contexto, corte nesta ordem de prioridade (do mais ao menos importante): fluxo do visitante → fluxo do vendedor → confirmação diária e expiração → administração → métricas. Diga explicitamente o que ficou de fora.

# 1. Problema e objetivo

Hoje as ofertas circulam em um grupo de WhatsApp. Exemplos reais do tipo de anúncio: cookies e brownies com sabores e preços; bolos de pote disponíveis naquele dia; últimas unidades de algum alimento; vendas pontuais, como dois patinetes; serviços oferecidos por estudantes.

As mensagens se perdem no histórico. Muitas não dizem onde retirar, quando está disponível ou se ainda está à venda.

A plataforma existe para que um visitante, sem cadastro, responda em segundos:
1. O que está sendo oferecido?
2. Quanto custa?
3. Está disponível agora ou é sob encomenda?
4. Onde e quando posso retirar ou receber?
5. Como falo com quem vende?

Critério central de sucesso: o visitante encontra uma oferta e sabe como comprá-la com pouco esforço; o vendedor mantém o anúncio atualizado sem precisar aprender um sistema complexo.

Modelo: uso gratuito, sem comissão. Eu custeio a hospedagem. Não implemente planos, assinaturas ou qualquer cobrança de vendedores. Comece com uma única comunidade; não construa infraestrutura para múltiplas instituições nesta versão.

# 2. Decisões já tomadas

Use como estão. Se discordar de alguma, justifique em uma frase e siga a sua alternativa.

- Idioma: interface em português do Brasil, com linguagem cotidiana e sem termos técnicos nas telas. Código, identificadores e mensagens de commit em inglês.
- Moeda: real (BRL). Armazene valores em centavos, como inteiro. Exiba no formato "R$ 12,50".
- Fuso da comunidade: America/Sao_Paulo, definido em um único lugar de configuração. [confirme]
- Contato: somente WhatsApp nesta versão. Gere links no formato `https://wa.me/55DDDNUMERO?text=...` com a mensagem codificada para URL. Valide o número no cadastro. O número só aparece publicamente com autorização explícita do vendedor.
- Autenticação: e-mail e senha para vendedores e administrador, com sessão em cookie HttpOnly. Não dependa de provedor de e-mail externo para a aplicação funcionar; se recuperação de senha exigir envio de e-mail, deixe preparado e documente como pendência.
- Cadastro de vendedor: aberto, mas o primeiro anúncio de cada vendedor só fica público após aprovação do administrador. [confirme; alternativa: código de convite]
- Categorias iniciais: Comidas e doces, Bebidas, Serviços, Objetos e usados, Outros. Editáveis pelo administrador, sem precisar mexer em código. [confirme]
- Imagens: até 3 fotos por anúncio, com limite de tamanho por arquivo. Redimensione e converta no upload, gerando pelo menos um tamanho para o cartão e um para a página da oferta. Valide o tipo real do arquivo, não apenas a extensão. Armazenamento em disco local ou em serviço compatível com S3, escolhido por variável de ambiente.
- Stack: escolha algo estável, econômico e fácil de manter por uma pessoa. Aplicação única, banco relacional e armazenamento de imagens. Prefira renderização no servidor com o mínimo de JavaScript no cliente. Deve subir localmente com um único comando (por exemplo, `docker compose up`) e publicar em um servidor ou plataforma barata (VPS pequena, Fly.io, Railway ou similar). Sem microsserviços, sem filas, sem infraestrutura que a escala atual não justifique. Justifique a escolha em um parágrafo.

# 3. Princípios obrigatórios de experiência

Aplique cada princípio em decisões concretas, não como declaração:

- Reconhecimento em vez de memorização: categorias visíveis, rótulos claros e contexto preservado ao voltar de um anúncio (filtros, busca e posição na lista).
- Divulgação progressiva: a lista mostra o necessário para decidir; os detalhes ficam na página da oferta.
- Hierarquia visual: produto, preço, disponibilidade, retirada ou entrega e ação principal se destacam, nesta ordem.
- Consistência: mesmos nomes, componentes e comportamentos em todas as telas.
- Feedback: confirme salvamento, publicação e mudança de disponibilidade. Mostre carregamento e falhas com clareza e em linguagem simples.
- Prevenção e recuperação de erros: valide campos, preserve o que foi preenchido após uma falha e permita corrigir sem recomeçar.
- Controle do usuário: editar, pausar e reativar anúncios deve ser trivial.
- Baixo esforço: o comprador não precisa de cadastro para navegar nem para abrir o contato.
- Acessibilidade: HTML semântico, navegação por teclado, foco visível, contraste mínimo de 4,5:1 para texto, campos com rótulos reais, alvos de toque de pelo menos 44 px. Nunca transmita status apenas por cor: use texto e, quando ajudar, ícone.

Proibido: carrosséis automáticos, pop-ups promocionais, animações excessivas, urgência falsa, contadores artificiais, avaliações inventadas e qualquer padrão de interface que manipule o usuário.

# 4. Estrutura das telas

## Página inicial

Nesta ordem de prioridade: identificação breve da plataforma e da comunidade; busca por produto, serviço ou vendedor; categorias simples; filtro "Disponíveis hoje"; lista de ofertas.

A lista deve aparecer rapidamente no celular. Nada de banner de apresentação ocupando a primeira tela.

Cada cartão mostra: uma foto; nome do produto ou serviço; preço, ou "A partir de" quando houver variações reais; nome do vendedor; disponibilidade; resumo de retirada ou entrega; uma ação principal clara.

Não mostre o cardápio inteiro no cartão. Evite elementos clicáveis sobrepostos e botões concorrentes. O cartão inteiro leva à página da oferta; um único botão secundário, no máximo.

## Página da oferta

Mostre foto(s), descrição curta, preço, variações, disponibilidade, condições de retirada ou entrega e identificação do vendedor, com link para a página dele.

Ação principal: "Consultar no WhatsApp". Abre uma mensagem já preenchida com o nome da oferta e, quando selecionada, a variação. Deixe claro, perto do botão, que disponibilidade, pagamento e entrega são combinados com o vendedor, e que abrir o WhatsApp não é um pedido confirmado.

Para alimentos, inclua campos de porção, ingredientes e alergênicos preenchidos pelo vendedor. Nunca deduza nem invente essas informações; se o vendedor não informou, mostre "Não informado pelo vendedor".

## Página do vendedor

Nome ou marca, apresentação curta, região atendida, horários informados e ofertas ativas. Botão para copiar ou compartilhar o link da página.

## Área do vendedor

Ao entrar, o vendedor vê imediatamente: seus anúncios; "Adicionar anúncio"; ações para editar, pausar, marcar como esgotado ou vendido; confirmação de disponibilidade do dia com um clique.

O formulário pede apenas o necessário e revela campos adicionais conforme o tipo de oferta. Use exemplos de preenchimento nos campos e marque os opcionais como "(opcional)". Salve rascunhos ou, no mínimo, preserve o preenchimento em caso de erro.

## Administração

Área mínima: aprovar o primeiro anúncio de cada vendedor, ocultar publicações inadequadas e tratar denúncias. Denúncia é feita por qualquer visitante, sem cadastro, com motivo em lista curta e campo livre opcional. Não construa painel com gráficos.

# 5. Tipos de oferta e regras de disponibilidade

Trate separadamente:

- Oferta recorrente: fica no catálogo, como um cardápio de cookies. Pode funcionar por encomenda sem estar disponível para retirada imediata.
- Oferta do dia: só aparece em "Disponíveis hoje" após o vendedor confirmar para aquela data. A confirmação expira às 23h59 do dia no fuso da comunidade ou no horário de encerramento informado, o que vier primeiro. Depois disso o anúncio pode continuar no catálogo, sem indicação de disponibilidade imediata. A expiração deve ser calculada no servidor no momento da leitura, comparando data e hora; não dependa de um job agendado para o estado ficar correto (um job de limpeza é opcional).
- Venda pontual: permanece ativa até ser pausada ou marcada como vendida. Se o vendedor não reconfirmar em 14 dias, o anúncio sai da lista pública e aparece na área do vendedor como "Precisa de confirmação", reativável com um clique. [confirme o prazo]

Estados visíveis ao público, quando aplicáveis: "Disponível hoje", "Sob encomenda", "Esgotado", "Vendido". Estado "Pausado" visível apenas ao vendedor. Diferencie com texto e ícone, nunca só com cor. Não apresente estoque como garantido: a negociação acontece fora da plataforma.

Atualizar deve ser tão fácil que o vendedor nunca precise recriar o anúncio.

# 6. Aparência e desempenho

Mobile-first, fundo claro, tipografia legível, uma cor principal, espaçamento consistente. Aparência acolhedora e organizada, sem excesso de decoração, gradientes, sombras ou cartões aninhados. As fotos dos produtos são o principal elemento visual.

Cuide dos estados: carregando, lista vazia, busca sem resultados (com sugestão de limpar filtros), imagem ausente (placeholder neutro, sem ícone quebrado), falha de conexão e anúncio indisponível ou removido.

Metas de desempenho: navegar, buscar e abrir o contato devem funcionar mesmo com JavaScript desativado; imagens com carregamento preguiçoso e tamanhos adequados; evite dependências pesadas. A experiência precisa funcionar bem em celulares modestos e conexões lentas.

# 7. Métricas e distribuição justa

A conversão principal é o início de contato com o vendedor. É um indicador de intenção, não comprovação de venda.

Registre de forma mínima e agregada por dia: visualizações de oferta, cliques para abrir o WhatsApp e buscas sem resultado (com o termo buscado). Não armazene IP, identificadores de dispositivo, conteúdo de conversas nem dados pessoais do visitante. Não use cookies para métricas.

Rodízio de exposição: a ordem da lista é estável durante a sessão de navegação e muda de um dia para o outro (por exemplo, embaralhamento com semente derivada da data). Ofertas compatíveis com busca e filtros sempre vêm antes; entre ofertas igualmente compatíveis, vale o rodízio. Não ordene por cliques nem por popularidade.

Não prometa aumento de vendas em nenhum texto. Estruture a plataforma para que seja possível testar se ela ajuda a gerar contatos e vendas relatadas pelos vendedores.

# 8. Segurança, privacidade e limites do MVP

Implemente:
- Autenticação simples para vendedores e administrador.
- Autorização no servidor: cada vendedor só altera os próprios dados; o administrador tem permissões distintas.
- Validação de entradas e de arquivos enviados; proteção contra CSRF.
- Limite de tentativas em login, formulários públicos (denúncia) e upload.
- Publicação de contato somente com autorização do vendedor, revogável a qualquer momento.
- O vendedor pode retirar anúncios da exposição pública e excluir a própria conta; a exclusão remove imediatamente a exposição pública.
- Valores monetários armazenados com precisão.

Não implemente nesta versão: checkout ou pagamentos; carrinho com múltiplos vendedores; chat interno; entregas próprias; cupons, pontos ou gamificação; avaliações públicas; inteligência artificial; importação automática de mensagens do WhatsApp; múltiplas comunidades.

# 9. Dados de demonstração

Crie um conjunto de dados fictícios, claramente identificados como exemplo (por exemplo, "Doces da Ana (exemplo)"), carregados apenas quando uma variável de ambiente de demonstração estiver ativa. Nunca publique nomes, contatos ou anúncios reais sem autorização.

# 10. Validação e entrega

1. Apresente em no máximo uma página: estrutura de telas, modelo mínimo de dados e as principais decisões de experiência. Depois implemente, sem esperar aprovação.
2. Valide os fluxos essenciais. Onde for viável, com testes automatizados; onde não for, com um roteiro manual que eu consiga repetir. Não invente resultados de testes.
   - Visitante encontra uma oferta e abre o contato sem cadastro.
   - Vendedor cria, edita e pausa um anúncio.
   - Confirmação diária expira corretamente, incluindo o caso do horário de encerramento informado.
   - Um vendedor não consegue alterar anúncios de outro, nem por requisição direta à API.
   - Formulários preservam o preenchimento quando ocorre uma falha.
   - A navegação funciona no celular e apenas com teclado.
3. Se houver acesso a usuários reais, proponha tarefas curtas de usabilidade e observe dificuldades. Não simule resultados.
4. Entregue: o código da aplicação; README com instruções de execução local e de publicação; um arquivo de exemplo com todas as variáveis de ambiente explicadas; e um resumo final com o que foi verificado, o que permanece pendente e as decisões e suposições tomadas ao longo do trabalho.

---

# Adendo do lead

## Identidade visual (obrigatória)

Fonte: `docs/produto/identidade/identidade-visual.pdf` (texto extraído em `identidade-visual.txt`, páginas renderizadas em `pagina-1.png` … `pagina-6.png`).

- **Nome:** "Pão de Cada Dia". Assinatura: "Compra e venda entre estudantes". Slogan: "Pra sobreviver ao Cálculo." Comunidade: "Campus Paraíso · MG" (UFLA/ICTIN).
- **Logo:** fatia de pão em forma de balão de conversa com três pontos (o "digitando…"). Abaixo de 24 px os pontos saem. Recriar em SVG simples.
- **Cores:** Azul Lavras `#1F4171` (primária: cabeçalho, botões principais); Verde Campus `#06713F` (preço, confirmação, "vendido"); Noite ICTIN `#050C45`; Ciano Circuito `#2EC4EA` (só sobre fundo escuro, nunca sobre branco). Neutros: Tinta `#0F1A2E` (texto), Grafite `#4A5468` (texto de apoio), Névoa `#E4E9F0` (linhas, campos), Papel `#F5F7FA` (fundo), Branco `#FFFFFF` (cartões), Azul 50 `#E8EEF7`, Verde 50 `#E3F2EA`. Estados: verde `#06713F`/`#E3F2EA`; âmbar `#9A5B00`/`#FFF4E0`; vermelho `#B42318`/`#FDECEA`.
- **Tipografia:** Barlow Condensed 500/600/700 para títulos e rótulos (rótulos em caixa alta, +14% de espaçamento); Source Sans 3 400/600/700 para texto. Preço: Source Sans 3 700, 22/24, números tabulares, em Verde Campus. Fontes servidas pelo próprio app (self-host, woff2), sem chamar o Google em tempo de execução.
- **Medidas:** raios 8 (selos), 12 (botões e campos), 16 (cartões), 999 (chips); espaços 4·8·12·16·24·32·48; toque mínimo 44×44; quase nenhuma sombra; campo em foco com borda Azul Lavras e halo Azul 50. Ícones de traço 2 px, cantos redondos.
- **Referência de tela:** página 5 do PDF (vitrine mobile: cabeçalho azul com logo, "O que tem no campus hoje?", busca, chips de categoria, lista de ofertas).

## Conflitos entre a identidade e o pedido — decisão do lead

O pedido do dono prevalece sobre o conteúdo das maquetes; a identidade vale para aparência.

1. A maquete mostra chat interno ("Conversas", "Chamar no chat", proposta/confirmar). **Fora**: o contato é só pelo WhatsApp. Ação principal = "Consultar no WhatsApp". Sem aba "Conversas" na navegação.
2. "MAIS PEDIDOS HOJE" ordena por popularidade. **Fora**: a lista usa o rodízio diário. Rótulo neutro (ex.: "OFERTAS" ou "DISPONÍVEIS HOJE" quando o filtro estiver ativo).
3. Estado "Reservado" e selo "NOVO HOJE" não existem no pedido. **Fora**. Estados públicos: Disponível hoje (verde), Sob encomenda (azul), Esgotado (âmbar), Vendido (neutro, preço riscado como na maquete). Só do vendedor: Pausado, Precisa de confirmação, Aguardando aprovação.
4. Categorias: as do pedido (Comidas e doces, Bebidas, Serviços, Objetos e usados, Outros), não as da maquete.
5. Modo noturno: fora do MVP.

## Critérios de aceite

- **CA1** Visitante sem cadastro busca por texto (produto, serviço ou vendedor), filtra por categoria e por "Disponíveis hoje", abre a oferta e aciona "Consultar no WhatsApp" com mensagem pré-preenchida (oferta e variação escolhida). Funciona com JavaScript desativado.
- **CA2** Ao voltar da oferta para a lista, busca, filtros e posição na lista são preservados (parâmetros na URL + âncora).
- **CA3** Cartão mostra foto (ou placeholder neutro), nome, preço ou "A partir de", vendedor, estado com texto e ícone, resumo de retirada/entrega; o cartão inteiro é um único link.
- **CA4** Página da oferta mostra fotos, descrição, preço, variações, estado, retirada/entrega, vendedor com link, aviso de que abrir o WhatsApp não confirma pedido; em alimentos, porção, ingredientes e alergênicos ou "Não informado pelo vendedor".
- **CA5** Página do vendedor com nome, apresentação, região, horários, ofertas ativas e botão de copiar/compartilhar link (com alternativa sem JavaScript).
- **CA6** Vendedor se cadastra com e-mail e senha, valida WhatsApp, dá ou revoga autorização para exibir o número; sem autorização, o número não aparece em nenhuma página pública nem no HTML.
- **CA7** Vendedor cria, edita, pausa, reativa, marca esgotado/vendido e confirma "disponível hoje" com um clique; recebe confirmação visível de cada ação.
- **CA8** Formulários preservam o preenchimento após erro de validação, com mensagens junto ao campo; campos extras aparecem conforme o tipo de oferta (alimento → porção, ingredientes, alergênicos; oferta do dia → horário de encerramento), também sem JavaScript.
- **CA9** Confirmação do dia expira às 23h59 no fuso configurado ou no horário de encerramento informado, o que vier primeiro, calculado na leitura (testado com relógio controlado, incluindo virada do dia).
- **CA10** Venda pontual sem reconfirmação há 14 dias some da lista pública e aparece ao vendedor como "Precisa de confirmação", reativável com um clique.
- **CA11** Um vendedor não consegue ver o formulário nem alterar anúncio ou foto de outro, inclusive por POST direto (resposta 404 ou 403, sem alteração no banco).
- **CA12** Primeiro anúncio de vendedor novo fica "Aguardando aprovação" até o administrador aprovar; admin oculta publicação, edita categorias e trata denúncias; visitante denuncia sem cadastro com motivo em lista e texto opcional.
- **CA13** Upload aceita até 3 fotos, valida tipo real e tamanho, gera ao menos dois tamanhos; armazenamento local ou S3 por variável de ambiente.
- **CA14** CSRF em todos os formulários; limite de tentativas em login, denúncia e upload; cookie de sessão HttpOnly.
- **CA15** Vendedor exclui a conta e todos os anúncios saem da exposição pública na hora.
- **CA16** Métricas agregadas por dia (visualizações, cliques no WhatsApp, buscas sem resultado com termo), sem IP, sem identificador, sem cookie.
- **CA17** Ordem da lista: compatíveis com busca/filtro primeiro; entre iguais, embaralhamento com semente da data (estável no dia, muda no dia seguinte); nunca por cliques.
- **CA18** Dados de demonstração marcados "(exemplo)", carregados só com variável de ambiente ativa.
- **CA19** `docker compose up` sobe o app localmente com banco; README com execução local e publicação; `.env.example` com todas as variáveis explicadas.
- **CA20** Acessibilidade: HTML semântico, navegação só por teclado, foco visível, contraste ≥ 4,5:1, rótulos reais, alvos ≥ 44 px, status nunca só por cor; identidade visual aplicada.
