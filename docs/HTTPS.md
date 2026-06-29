# Servindo o InvenSync por HTTPS

O app roda em HTTP (waitress, porta 5090). Para HTTPS, coloque um **proxy reverso**
na frente que termina o TLS e encaminha para o waitress. O app já está preparado:

1. No `.env`, ligue:
   ```
   BEHIND_PROXY=1
   SESSION_COOKIE_SECURE=1
   ```
   - `BEHIND_PROXY=1` faz o Flask honrar os cabeçalhos `X-Forwarded-*` (gera URLs
     `https://` corretas).
   - `SESSION_COOKIE_SECURE=1` envia os cookies de sessão/lembrar-me só por HTTPS.
2. Mantenha o waitress ouvindo só local quando houver proxy: `SERVE_HOST=127.0.0.1`.
3. Reinicie o serviço.

> ⚠️ Só ligue `SESSION_COOKIE_SECURE=1` depois que o HTTPS estiver funcionando;
> caso contrário os cookies não serão enviados em HTTP e ninguém consegue logar.

## Opção A — Caddy (mais simples)
`Caddyfile`:
```
invensync.suaempresa.local {
    reverse_proxy 127.0.0.1:5090
}
```
Caddy resolve o certificado automaticamente (domínio público) ou use um certificado
interno (`tls /caminho/cert.pem /caminho/key.pem`). Rode `caddy run`.

## Opção B — IIS (Windows Server, já presente)
1. Instale **URL Rewrite** e **Application Request Routing (ARR)** (Web Platform Installer).
2. Em ARR, habilite *Enable proxy*.
3. Crie um site/binding **HTTPS (443)** com o certificado (interno da AD CS ou comercial).
4. Adicione uma regra de *Reverse Proxy* apontando para `http://127.0.0.1:5090`.
5. Garanta que o ARR encaminhe os cabeçalhos `X-Forwarded-Proto`/`X-Forwarded-For`
   (em ARR: *Server Proxy Settings → Preserve client IP / Add X-Forwarded-For*).

## Opção C — nginx (Windows)
```nginx
server {
    listen 443 ssl;
    server_name invensync.suaempresa.local;
    ssl_certificate     C:/certs/invensync.crt;
    ssl_certificate_key C:/certs/invensync.key;
    location / {
        proxy_pass http://127.0.0.1:5090;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
# (opcional) redireciona HTTP -> HTTPS
server { listen 80; server_name invensync.suaempresa.local; return 301 https://$host$request_uri; }
```

## Verificação
- Acesse `https://.../` — cadeado válido.
- Faça login; confirme nos DevTools (Application → Cookies) que `session` e
  `remember_token` estão com a flag **Secure**.
