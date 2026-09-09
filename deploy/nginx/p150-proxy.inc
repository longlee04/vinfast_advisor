# Phan proxy dung chung cho ca bon location (prod/staging x api/fe).
# Tach ra file rieng de sua mot cho la ca bon cho doi theo.

proxy_http_version 1.1;

proxy_set_header Host              $host;
proxy_set_header X-Real-IP         $remote_addr;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
# Backend doc header nay de biet request goc la https; thieu no thi cookie
# `Secure` va cac duong dan redirect se sinh ra nham thanh http.
proxy_set_header X-Forwarded-Proto $scheme;

# SSE cho luot tu van: nginx mac dinh gom het roi moi tra mot cuc, khien man
# chat dung im vai chuc giay roi hien tron ven — nhin nhu treo.
proxy_buffering off;
proxy_cache off;

# Mot luot tu van co the mat den vai chuc giay (nhieu lan goi LLM). Mac dinh
# 60s cua nginx se cat ngang giua chung.
proxy_read_timeout 300s;
proxy_send_timeout 300s;

# WebSocket cho HMR cua Next tren staging.
proxy_set_header Upgrade    $http_upgrade;
proxy_set_header Connection "upgrade";
