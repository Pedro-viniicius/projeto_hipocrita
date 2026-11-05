# Roteiro manual de validação

O que os testes automáticos não conseguem provar. Escrito pelo `qa` em 2026-11-05 e atualizado depois das correções do MVP. Repita antes de cada publicação importante.

**Antes de começar:** rode `docker compose up` e abra http://localhost:8000. Os dados de exemplo carregam sozinhos. Para criar o admin: `docker compose exec web python manage.py createsuperuser`. Use o Chrome.

**Celular:** o site local só aceita conexões da própria máquina, então um celular na mesma rede não abre. Use uma destas opções:
- Android por USB, com `chrome://inspect` e encaminhamento da porta 8000.
- Um túnel HTTPS (cloudflared, ngrok), com `ALLOWED_HOSTS=<host do túnel>` e `CSRF_TRUSTED_ORIGINS=https://<host do túnel>` no `.env`.
- Só para o bloco D: abrir o link do `wa.me` no WhatsApp Web do computador.

**Contas:** o admin criado com `createsuperuser` não tem perfil de vendedor, e "Meus anúncios", "Novo anúncio", "Perfil" e "Excluir conta" dão 403 para ele. Use duas contas: uma de vendedor, pelo cadastro, e a do admin.

**Limites de tentativas:** repetir o roteiro pode bloquear você (5 envios de cadastro por hora, contando os com erro, e 5 falhas de login em 15 min). Para desbloquear no ambiente local: `docker compose exec web python manage.py shell -c "from apps.core.models import RateLimitCounter as R; R.objects.all().delete()"`.

Marque cada passo como ✅ ou ❌ e anote o que viu.

## A. Teclado (computador)
1. Abra a página inicial e aperte Tab uma vez.
   - **Esperado:** aparece "Pular para o conteúdo", com foco bem visível. Enter leva o foco ao conteúdo.
2. Aperte Tab várias vezes.
   - **Esperado:** a ordem é marca, "Vender aqui", busca, Buscar, categorias, "Disponíveis hoje", um foco por cartão e o rodapé. O foco nunca some nem fica preso.
3. Na busca, digite "calculo" e aperte Enter. Escolha uma categoria e abra uma oferta com Enter.
   - **Esperado:** "Voltar para a lista" volta com a busca e o filtro, e a página rola até o cartão.
4. Na oferta, escolha uma variação com as setas e aperte Enter em "Consultar no WhatsApp".
   - **Esperado:** abre uma aba do wa.me com a mensagem preenchida, incluindo a variação.
5. Repita o Tab em Entrar e Cadastrar. Com a conta de vendedor, em Meus anúncios, Novo anúncio, Perfil e Excluir conta. Com a conta de admin, em `/admin/`.
   - **Esperado:** o primeiro Tab é sempre "Pular para o conteúdo", e tudo funciona com Enter ou Espaço.
6. Preencha o formulário de anúncio só com o teclado.
   - **Esperado:** as seções "oferta do dia" e "alimento" aparecem conforme o tipo e a categoria escolhidos.

## B. Leitor de tela (NVDA, VoiceOver ou TalkBack)
1. Abra a página inicial.
   - **Esperado:** o título, a busca, as categorias (a ativa anunciada como atual) e a lista são lidos em ordem lógica.
2. Percorra os cartões.
   - **Esperado:** cada cartão é um link único, com nome, preço, estado em texto, vendedor e retirada.
3. Envie o cadastro com o WhatsApp errado.
   - **Esperado:** o leitor anuncia o resumo dos erros e o erro do campo.
4. Em "Meus anúncios", vá até "Mais ações".
   - **Esperado:** o nome lido inclui o título do anúncio.

## C. Celular real
1. Abra a página inicial.
   - **Esperado:** a lista aparece logo, sem rolagem horizontal. Os chips de categoria ficam numa linha que rola de lado.
2. Toque em chips, botões e links.
   - **Esperado:** todos são fáceis de acertar com o dedo, e os campos não dão zoom automático.
3. Aplique zoom de 200%.
   - **Esperado:** nada fica cortado nem sobreposto.
4. Gire a tela.
   - **Esperado:** o layout se adapta.
5. Faça uma busca, abra uma oferta e use o Voltar do sistema.
   - **Esperado:** você volta com a busca, o filtro e a posição na lista.

## D. WhatsApp real
1. Crie um vendedor com o seu número e marque a autorização. Crie um anúncio, aprove pelo admin e abra o anúncio no celular.
   - **Esperado:** o WhatsApp abre com a mensagem pronta e o endereço da oferta.
2. No perfil, escolha "não mostrar meu número".
   - **Esperado:** a oferta some da vitrine na hora.

## E. Contraste e foco
1. Rode o Lighthouse ou o inspetor de contraste na página inicial, numa oferta, no formulário e no painel.
   - **Esperado:** texto com contraste de pelo menos 4,5:1.
2. Navegue com o teclado.
   - **Esperado:** o foco fica visível em todos os elementos, inclusive sobre o cabeçalho azul.
3. Confira os estados das ofertas.
   - **Esperado:** cada estado tem texto e ícone, nunca só cor.

## F. Vendedor e admin com JavaScript desligado
1. Cadastre-se, crie um anúncio com foto e variação, edite e pause.
   - **Esperado:** tudo funciona.
2. Escolha "Oferta do dia" e uma categoria de comida.
   - **Esperado:** aparecem as seções de horário e de alimento.
3. Entre como admin. Aprove, oculte e mostre um anúncio, e trate uma denúncia.
   - **Esperado:** cada passo aparece na vitrine na hora.
4. Marque como esgotada uma oferta do dia e confira a vitrine hoje e amanhã.
   - **Esperado:** hoje ela mostra o selo "Esgotado". Amanhã continua listada, sem selo e sem botão de contato.

## G. Armazenamento S3
1. Configure `STORAGE_BACKEND=s3` com um bucket real e envie 3 fotos.
   - **Esperado:** as fotos aparecem na vitrine, ficam no bucket, e a URL deixa de valer depois de excluir a foto ou a conta. Com o armazenamento local, o navegador ou uma CDN ainda pode mostrar a foto excluída por até 24 h.
2. Envie um PDF renomeado para `.jpg`.
   - **Esperado:** o arquivo é recusado, com a mensagem junto do campo.

## H. Publicação
1. Siga o README numa máquina limpa (`compose.prod.yaml`).
   - **Esperado:** o site responde em HTTPS, os cookies saem `Secure` e HttpOnly, e `/healthz` responde 200.
2. Abra `/privacidade/`.
   - **Esperado:** nome e e-mail do responsável preenchidos, sem "a definir" (README, passo 6).
3. Abra a vitrine.
   - **Esperado:** nenhuma oferta "(exemplo)". Se o banco veio do ambiente local, rode `load_demo --remove`.
4. Veja os logs de subida.
   - **Esperado:** `cleanup_data` aparece, e o cron de hora em hora está configurado (README).
5. Sem SMTP configurado, abra a tela de entrar e `/senha/recuperar/`.
   - **Esperado:** o link "Esqueceu a senha?" não aparece, as duas telas mostram o e-mail de contato do responsável, e `docker compose logs web` não mostra token (só `/senha/redefinir/***`). Em ambiente local (`DEBUG=true`), o fluxo funciona e o e-mail aparece no log.
6. Erre a senha 6 vezes num aparelho e tente entrar de outro aparelho, em outra rede.
   - **Esperado:** o primeiro recebe "muitas tentativas" (429), e o outro entra normalmente: o limite conta pelo IP real.
7. **Rede do campus:** conecte dois aparelhos ao Wi-Fi do campus e compare o IP público de cada um (por exemplo, em um site que mostra "qual é meu IP").
   - **Esperado:** IPs diferentes. Se forem iguais, os limites por IP valem para todos juntos: reavalie login, contato e cadastro (`docs/produto/decisoes.md`).
8. Abra o cadastro depois de atingir `SIGNUPS_PER_DAY` (padrão 50; o dia vira às 21h de Brasília).
   - **Esperado:** a tela avisa do limite, sem formulário.
9. Suba com `SIGNUPS_PER_DAY=0` e abra o cadastro.
   - **Esperado:** a tela diz que o cadastro está fechado, sem formulário, sem data de reabertura, e mostra o contato do responsável (ou diz que ainda não há contato).

## I. Vercel (plano Hobby)
Só depois da publicação, no domínio de produção (`https://<projeto>.vercel.app`). Os testes automáticos cobrem a rota, o build, o workflow e o servidor com `MAX_UPLOAD_MB=1`; o que segue depende da plataforma ou de um navegador real. Para as fotos, use um celular de verdade (Android com Chrome e iPhone com Safari), no 4G e no Wi-Fi.

**Fotos reduzidas no navegador (`static/js/fotos.js`)**
1. Em "Novo anúncio", escolha 3 fotos tiradas agora pela câmera do celular (cada uma com mais de 3 MB).
   - **Esperado:** aparece "Preparando as fotos…" por alguns segundos e some; o botão "Salvar" fica desabilitado nesse intervalo. Salvar funciona e as 3 fotos aparecem no anúncio, com a orientação certa (retrato em pé, não deitado).
2. Tire uma foto na vertical e salve.
   - **Esperado:** a foto sai em pé, sem giro.
3. Escolha uma foto com localização ligada na câmera, salve o anúncio e abra a foto pública (baixe o arquivo).
   - **Esperado:** sem GPS nem marca da câmera nos metadados (o servidor também os remove).
4. Escolha as fotos, toque em "Salvar" no meio do "Preparando as fotos…".
   - **Esperado:** nada é enviado ainda; o envio só ocorre quando o aviso some.
5. Escolha 3 fotos, abra o seletor de novo e cancele (ou escolha outras).
   - **Esperado:** o botão volta ao normal; vale a última escolha.
6. Escolha 3 PNG de captura de tela com transparência.
   - **Esperado:** viram JPEG com fundo branco (não preto).
7. No iPhone, escolha uma foto em formato HEIC (da galeria, "Todas as fotos").
   - **Esperado:** salva (o Safari entrega JPEG) ou, se algum navegador não converter, a mensagem do app ("Este arquivo não é uma foto válida…"). Nunca uma página em branco nem a página de erro da Vercel.
8. Escolha mais de 3 fotos de uma vez.
   - **Esperado:** a mensagem do app "Até 3 fotos…", sem perder o texto já digitado.
9. Abra a tela, vá para outra página e volte pelo botão "Voltar" do navegador.
   - **Esperado:** o botão "Salvar" não fica travado.
10. Com JavaScript desligado (Chrome: Configurações do site → JavaScript → Bloquear), envie 1 foto de 3 MB e depois 3 fotos de 1,3 MB cada.
    - **Esperado:** a 1ª e a 2ª mostram "Esta foto passou de 1 MB. Escolha uma menor." na página do app; nada de 500, nada de página da Vercel. Com 3 fotos de 1,5 MB (corpo acima de 4 MiB) aparece "Envio grande demais", também do app.
11. (Observação, não é defeito do app) Com JavaScript desligado e 3 fotos de 5 MB, a Vercel responde com a página dela (corpo acima de 4,5 MB). Anote o que aparece.

**Teste de fumaça (README, "Teste de fumaça")**
12. `/` e `/healthz` dão 200; o CSS tem hash no nome; `/privacidade/` mostra o responsável e o parágrafo sobre "a empresa que hospeda o site".
13. `curl -i https://<projeto>.vercel.app/_tarefas/limpeza/` dá 401; `curl -i -H "Authorization: Bearer errado" ...` também dá 401; `curl -i -X POST ...` dá 405.
14. Cron da Vercel: Settings → Cron Jobs → View Log, depois do 1º horário das 06:07 UTC.
    - **Esperado:** status 200. Se aparecer 400, a Vercel chamou por um endereço que não está em `ALLOWED_HOSTS` (veja o domínio usado no log e acrescente-o). Se aparecer 401, o `CRON_SECRET` mudou depois do último deploy.
15. GitHub → Actions → "Limpeza de dados vencidos" → Run workflow.
    - **Esperado:** termina em verde; o log não mostra o segredo. Depois, confira que as execuções agendadas (de 30 em 30 minutos, com algum atraso normal do GitHub) aparecem e passam. Se falhar, a mensagem mostra só o status HTTP: veja o diagnóstico no README (Vercel, passo 9).
16. 6 logins errados num aparelho dão 429; de outro aparelho, em outra rede (4G), o login continua liberado.
17. Nos cabeçalhos: CSP, HSTS (depois de ligar `SECURE_HSTS_SECONDS`) e cookies `Secure`. `curl -I http://<projeto>.vercel.app/` redireciona para `https://`.
18. Anúncio com fotos: as imagens carregam do R2 sem erro de CSP no console do navegador (acrescente o endereço do R2 em `CSP_EXTRA_IMG_SRC` se faltar).
19. Painel da Vercel → Logs: faça uma busca por "banana" no site.
    - **Esperado:** o termo aparece no log da plataforma, como a página de privacidade avisa. Confirme que não há o número de WhatsApp em nenhum log (o 302 de `/oferta/<id>/whatsapp/` não aparece com o número).

## Teste com usuários reais (seção 10.3 do pedido)
Ainda não houve teste com usuários. Quando houver acesso, observe 3 a 5 pessoas da comunidade fazendo, sem ajuda:
1. "Ache algo doce que dá para comprar hoje e chame quem vende."
2. "Descubra onde retirar o bolo de pote e até que horas ele está disponível."
3. (vendedor) "Anuncie seus brownies com dois sabores e preços diferentes."
4. (vendedor) "Seu brownie acabou: avise na plataforma."
5. (vendedor) "Amanhã você vai ter bolo de novo: deixe isso visível."

Anote onde a pessoa hesitou, errou ou pediu ajuda. Registre o que observou, sem interpretar além disso.
