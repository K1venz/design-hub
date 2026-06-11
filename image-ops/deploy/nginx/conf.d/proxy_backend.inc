# 反代到后端的公共指令块（/api 去前缀）。
# 被 location /api/ 及限流子路径(/api/auth/*) include 共享，避免逐字重复导致漂移。
# 命名 .inc 而非 .conf —— nginx.conf 的 `include conf.d/*.conf` 不会把它当独立配置自动加载
# （本片段只含 location 内合法指令，单独加载会语法报错）。
rewrite ^/api/(.*)$ /$1 break;
proxy_pass http://design_hub_api;
proxy_http_version 1.1;
proxy_set_header Host              $host;
proxy_set_header X-Real-IP         $remote_addr;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
# SSE 友好（/api/generate/* 异步出图进度）
proxy_buffering           off;
proxy_cache               off;
proxy_read_timeout        3600s;
proxy_send_timeout        3600s;
chunked_transfer_encoding on;
