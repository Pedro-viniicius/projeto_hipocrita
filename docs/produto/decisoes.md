# Decisões do dono

Decisão registrada não se reabre sem fato novo.

## 2026-11-05 — Itens "[confirme]" do brief `vitrine-mvp`

Confirmados pelo dono (versão revisada do pedido, com o corpo idêntico ao do brief):

1. **Fuso da comunidade:** `America/Sao_Paulo`, em um único lugar de configuração.
2. **Cadastro de vendedor:** aberto. O primeiro anúncio de cada vendedor só fica público depois da aprovação do administrador. Não usar código de convite.
3. **Categorias iniciais:** Comidas e doces, Bebidas, Serviços, Objetos e usados, Outros. O administrador pode editá-las sem mexer em código.
4. **Reconfirmação de venda pontual:** 14 dias. Depois disso, o anúncio sai da lista pública e aparece como "Precisa de confirmação", reativável com um clique.

## 2026-11-05 — Identidade visual

- Usar a identidade "Pão de Cada Dia" (`docs/produto/identidade/identidade-visual.pdf`) na aparência.
- Onde as maquetes contrariam o pedido, vale o pedido: sem chat interno, sem "mais pedidos", sem estado "Reservado" nem selo "Novo hoje". Modo noturno fica fora do MVP. Detalhes no adendo de `docs/produto/briefs/vitrine-mvp.md`.

## 2026-11-05 — Suposições do lead (aguardam validação do dono na entrega)

Resolvem as perguntas em aberto da spec `docs/produto/specs/vitrine-mvp.md`:

1. **Anúncio sem WhatsApp autorizado não fica público.** A pergunta "como falo com quem vende?" é central. O vendedor pode criar e editar anúncios, mas eles só entram na lista pública quando ele autoriza exibir o WhatsApp. Se revogar, os anúncios saem da exposição pública na hora e a área do vendedor explica o motivo.
2. **Recuperação de senha:** o fluxo com token e envio por e-mail está pronto, mas só funciona com SMTP configurado. Em produção sem SMTP ele fica desligado e a tela de entrada mostra o e-mail de contato, ou diz que ainda não há contato (o link com token nunca vai para o log). Substitui a suposição anterior, de mandar o e-mail para o log do console, reprovada na revisão de segurança (S3).
3. **Página "Privacidade":** texto factual sobre o que é guardado, base legal e prazos. Nome e e-mail do responsável vêm de `PRIVACY_CONTROLLER_NAME` e `PRIVACY_CONTACT_EMAIL`; vazios, a página mostra "a definir" e `check --deploy` avisa. O dono ainda precisa revisar o texto e informar o responsável antes de publicar (o aviso de rascunho saiu da página pública).
4. **Fotos:** até 5 MB por arquivo, 3 por anúncio.
5. **Logo:** SVG da spec; pode ser refinado depois.

## 2026-11-05 — Decisões do lead na rodada de correções (aguardam validação do dono na entrega)

1. **Categoria escondida:** só o chip some. As ofertas dela continuam em "Tudo" e na busca.
2. **Oferta do dia esgotada:** o selo "Esgotado" aparece só no dia em que foi marcado. Nos dias seguintes, sem confirmação, fica sem selo. Ressalva à D11 do plano.
3. **Pausar um anúncio esgotado e reativar:** volta para ativo.
4. **Tetos contra abuso:** 30 anúncios por vendedor; 3 pendentes e 12 fotos por hora para quem ainda não foi aprovado (20 fotos por hora depois da aprovação); `SIGNUPS_PER_DAY` cadastros por dia no site inteiro (padrão 50); 60 contatos por hora por IP.
5. **Troca de nome do vendedor:** o endereço público muda junto, e o antigo passa a dar 404, sem redirecionamento. O perfil avisa.
6. **Guarda de dados:** buscas sem resultado por 90 dias; texto de denúncia tratada por 180 dias; sessões vencidas são apagadas (`cleanup_data`).
7. **E-mail `.invalid`:** recusado no cadastro, porque esse domínio é reservado para as contas de exemplo.

## 2026-11-05 — Decisões do dono na entrega do MVP

1. **Responsável pelos dados:** nome e e-mail são definidos na publicação. Até lá, a página de privacidade mostra "a definir" e as telas dizem que ainda não há contato. Preencher `PRIVACY_CONTROLLER_NAME` e `PRIVACY_CONTACT_EMAIL` antes de divulgar: o `check --deploy` avisa, mas o app sobe mesmo sem eles.
2. **Risco aceito (S6):** o cadastro continua avisando quando um e-mail já tem conta. Isso revela só que a pessoa vende, e o nome de quem vende já é público.
3. **Limites por IP e rede do campus:** os valores ficam como estão até testar se o Wi-Fi do campus sai por um único IP público (item H do `docs/roteiro-manual.md`). Se sair, reavaliar os limites de login (5 falhas em 15 min), contato (60 por hora) e cadastro (5 por hora).

## 2026-11-05 — Publicação na Vercel (plano `docs/produto/planos/publicar-vercel.md`)

1. **Plano Hobby (gratuito).** O dono escolheu o Hobby sabendo que os termos da Vercel o restringem a uso pessoal não comercial e citam "advertising the sale of a product or service". **Risco aceito pelo dono:** a Vercel pode suspender o projeto; a saída é migrar para o Pro ou para o Docker (README). No Hobby o cron da Vercel roda no máximo 1 vez por dia, então a limpeza frequente vem de um agendamento do GitHub Actions de 30 em 30 minutos (etapa 7 do plano; o Actions atrasa e pode ser desligado após 60 dias sem atividade).
2. **Fotos de até 1 MB no servidor.** O navegador reduz as fotos antes de enviar (limite de 4,5 MB por requisição da Vercel). Sem JavaScript, foto acima de 1 MB é recusada com a mensagem do app.
3. **Privacidade:** aprovado o texto que diz que a empresa de hospedagem registra cada acesso (página, termo buscado, navegador e IP) por conta própria, por prazo curto.
4. **Dados fora do Brasil:** aceito que Vercel (logs de acesso) e Cloudflare R2 (fotos) processem dados; site e banco ficam em São Paulo.
5. **Prazo dos contadores na privacidade (decisão do lead, rodada 2 da revisão):** a página diz "em até 24 horas; se a limpeza automática falhar, em até 2 dias". Na Vercel, o piso garantido é o cron diário (vence com 23 h + até ~25 h). Em VPS/Docker, o "2 dias" depende do cron de hora em hora do README estar ativo.
