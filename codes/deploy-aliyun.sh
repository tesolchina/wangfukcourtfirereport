#!/bin/bash
# Deploy Wang Fuk Court Fire Report static site to Aliyun ECS + nginx
# Follows the deploy-to-aliyun skill pattern.
# Run this on the target Aliyun server (after git clone / subtree of the FireReport content).

set -e

APP_NAME="wangfukcourtfirereport"
DEPLOY_DIR="/opt/${APP_NAME}"
WEB_ROOT="/var/www/${APP_NAME}"
DOMAIN="wangfukcourtfirereport.simonsays.hk"
NGINX_CONF="/etc/nginx/sites-available/${APP_NAME}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${APP_NAME}"

echo "=== Deploying Fire Report site to Aliyun (static via nginx) ==="

# 1. Ensure we are in the FireReport checkout
if [ ! -f "site/index.html" ]; then
    echo "Error: Run this script from inside the FireReport directory (or after subtree clone)."
    exit 1
fi

echo "Deploy dir: $DEPLOY_DIR"
echo "Web root: $WEB_ROOT"

# 2. Update code on server (this script is usually run after a fresh clone/pull by the server-side process)
# For manual / first deploy:
sudo mkdir -p "$DEPLOY_DIR"
sudo rsync -a --delete ./ "$DEPLOY_DIR/"   # or the server does git clone here

cd "$DEPLOY_DIR"

# 3. Prepare web root (only the static assets we want to serve)
sudo mkdir -p "$WEB_ROOT/data"
sudo cp -f site/index.html "$WEB_ROOT/index.html"
sudo cp -f data/index.json "$WEB_ROOT/data/"
sudo cp -f data/relationships.md "$WEB_ROOT/data/" 2>/dev/null || true
# Note: large images/markdown/pdfs are NOT copied here (they stay in repo or OSS private if needed)

# 4. Write nginx config for the custom domain + static serving
sudo tee "$NGINX_CONF" > /dev/null <<NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    root ${WEB_ROOT};
    index index.html;

    location / {
        try_files \$uri \$uri/ =404;
    }

    location /data/ {
        alias ${WEB_ROOT}/data/;
        autoindex off;
    }

    # Optional: cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
NGINX

# Enable site
sudo ln -sf "$NGINX_CONF" "$NGINX_ENABLED"

# 5. Test and reload nginx
sudo nginx -t
sudo systemctl reload nginx || sudo service nginx reload

echo ""
echo "✅ Deploy complete!"
echo "Site should be available at: http://${DOMAIN}"
echo ""
echo "Next (domain mapping via aliyun CLI):"
echo "  aliyun alidns UpdateDomainRecord --RecordId <id> --RR wangfukcourtfirereport --Type A --Value <ECS_PUBLIC_IP>"
echo ""
echo "For HTTPS: use aliyun cas or certbot on the server."
echo "Done."