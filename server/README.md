# Servidor ProxiSense (AWS)

Recibe el estado y las alertas desde casa y los muestra en un panel web protegido con contraseña:
estado en línea/sin señal de cada dispositivo, mapa de calor 8×8, alertas recientes y actividad de las últimas 24 h.

```
Casa: sensor ──> equipo con proxisense.py ──HTTPS──> AWS (este servidor) <── tu navegador
                         └──> Telegram (las alertas siguen llegando aunque AWS esté caído)
```

El servidor nunca se conecta al sensor: los datos llegan por HTTPS desde casa con una clave.

## Qué necesitas

- La instancia Ubuntu en AWS (la que ya tienes).
- Un nombre de dominio para tener HTTPS. Gratis: crea un subdominio en [duckdns.org](https://www.duckdns.org) y apúntalo a la IP de la instancia.

## Despliegue paso a paso

### 1. Red de la instancia (Security Group)

En la consola de AWS: EC2 → tu instancia → Seguridad → grupo de seguridad → *Editar reglas de entrada*:

| Puerto | Origen | Para qué |
| --- | --- | --- |
| 22 (SSH) | Mi IP | administrar la instancia |
| 80 (HTTP) | Cualquier lugar | Caddy necesita el 80 para obtener el certificado |
| 443 (HTTPS) | Cualquier lugar | el panel y los envíos desde casa |

El puerto 8000 **no** se abre: el servidor solo escucha dentro de la instancia y Caddy lo expone.

Recomendado: asociar una *Elastic IP* a la instancia (EC2 → Direcciones IP elásticas), para que la IP no cambie al reiniciarla. Luego en DuckDNS pon esa IP en tu subdominio.

### 2. Instalar el programa

Conéctate por SSH y ejecuta:

```bash
sudo apt update && sudo apt install -y python3-venv git
sudo git clone https://github.com/Scontreras17/ProxiSense.git /opt/proxisense
cd /opt/proxisense
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r server/requirements.txt
```

Si el repositorio es privado, `git clone` te pedirá credenciales. En ese caso, crea un *token de acceso personal* en GitHub (Settings → Developer settings) con permiso de solo lectura y úsalo como contraseña, o copia la carpeta con `scp -r`.

### 3. Crear las claves

```bash
# Genera una clave larga para los dispositivos y anótala:
openssl rand -hex 24
sudo nano /etc/proxisense.env
```

Contenido del archivo (cambia los valores):

```
PROXISENSE_API_KEY=pega_aqui_la_clave_generada
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=una_contraseña_larga_y_unica
```

```bash
sudo chmod 600 /etc/proxisense.env
```

Sin estas dos claves el servidor rechaza todo, en vez de quedar abierto.

### 4. Dejarlo corriendo como servicio

```bash
sudo cp /opt/proxisense/server/proxisense-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now proxisense-server
sudo systemctl status proxisense-server     # debe decir "active (running)"
curl http://127.0.0.1:8000/healthz          # debe responder {"status":"ok"}
```

### 5. HTTPS con Caddy

Instala Caddy (instrucciones oficiales para Ubuntu; si cambian, están en caddyserver.com/docs/install):

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Copia `server/Caddyfile` a `/etc/caddy/Caddyfile`, cambia `tu-dominio.duckdns.org` por tu dominio y recarga:

```bash
sudo cp /opt/proxisense/server/Caddyfile /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Abre `https://tu-dominio.duckdns.org` en el navegador: te pedirá usuario y contraseña (los del paso 3).

### 6. Conectar el monitor de casa

En el `.env` del equipo que tiene el sensor:

```
PROXISENSE_SERVER_URL=https://tu-dominio.duckdns.org
PROXISENSE_API_KEY=la_misma_clave_del_paso_3
PROXISENSE_DEVICE=casa-sala
```

y ejecuta `python proxisense.py`. En unos segundos aparece el dispositivo "EN LÍNEA" en el panel.

## Actualizar el servidor más adelante

```bash
cd /opt/proxisense && sudo git pull && sudo systemctl restart proxisense-server
```

## API para otros dispositivos (por ejemplo una ESP32)

Cualquier dispositivo con Wi-Fi puede reportar con dos llamadas HTTPS y la cabecera `X-API-Key`. El servidor pone la hora, así que el dispositivo no necesita reloj.

Estado (cada 5 a 10 s). `frame` es opcional: 64 distancias en mm si el dispositivo tiene una matriz 8×8.

```bash
curl -X POST https://tu-dominio.duckdns.org/api/heartbeat \
  -H "X-API-Key: TU_CLAVE" -H "Content-Type: application/json" \
  -d '{"device":"esp32-pasillo","nearest_mm":420,"cells_near":1}'
```

Evento. `kind` es `alert` (aviso enviado), `presence` (detectado pero silenciado) o `info`:

```bash
curl -X POST https://tu-dominio.duckdns.org/api/events \
  -H "X-API-Key: TU_CLAVE" -H "Content-Type: application/json" \
  -d '{"device":"esp32-pasillo","kind":"alert","distance_mm":420,"message":"Movimiento en el pasillo"}'
```

## Seguridad y límites

- El panel y las claves viajan por HTTPS (Caddy). No uses el panel por `http://` desde fuera.
- Las claves están en `/etc/proxisense.env`, nunca en el código ni en GitHub.
- Si una clave se filtra, cámbiala en ese archivo y ejecuta `sudo systemctl restart proxisense-server`.
- El historial de eventos se conserva 90 días (`PROXISENSE_RETENTION_DAYS`).
- El servidor no limita la cantidad de intentos de contraseña. Usa una contraseña larga.
- Una instancia `t3.micro` o `t4g.micro` sobra para este uso.
