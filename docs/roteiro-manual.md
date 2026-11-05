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

## Teste com usuários reais (seção 10.3 do pedido)
Ainda não houve teste com usuários. Quando houver acesso, observe 3 a 5 pessoas da comunidade fazendo, sem ajuda:
1. "Ache algo doce que dá para comprar hoje e chame quem vende."
2. "Descubra onde retirar o bolo de pote e até que horas ele está disponível."
3. (vendedor) "Anuncie seus brownies com dois sabores e preços diferentes."
4. (vendedor) "Seu brownie acabou: avise na plataforma."
5. (vendedor) "Amanhã você vai ter bolo de novo: deixe isso visível."

Anote onde a pessoa hesitou, errou ou pediu ajuda. Registre o que observou, sem interpretar além disso.
