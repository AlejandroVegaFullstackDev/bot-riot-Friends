# Discord Bot — Slash + Automatizaciones (Español)

Incluye:
- Slash: `/ping`, `/server-info`, `/user-info`, `/kick`, `/ban`, `/dice`, `/rps`, `/poll`.
- Automatizaciones tipo "handlers":
  1) **Down**: Si alguien escribe exactamente `Down` o `Server en decadencia` y NO tiene roles protegidos, se le asigna el rol `BAD_BEHAVIOR_ROLE_ID`.
  2) **Presentaciones**: Si alguien postea **una imagen** en `#presentaciones`, el bot reacciona con emojis configurados.
  3) **Boost Loss**: Al perder el rol `Server Booster`, se **quitan** los roles de beneficios y se **avisa** a `#staff`.
  4) **Boost Add**: Al ganar `Server Booster`, se envía un **mensaje/embebido** a `#general` con beneficios.

> **Importante:** Activa en el portal de Discord **Privileged Gateway Intents**:
> - *SERVER MEMBERS INTENT* ✅ (para roles y /user-info)
> - *MESSAGE CONTENT INTENT* ✅ (necesario para leer texto y reaccionar en Presentaciones y "Down").

## Pasos rápidos
1. Crea entorno virtual e instala dependencias:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # Linux/Mac:
   # Hydra Bot (bot-riot-Friends)

   Documentación en español para el bot Discord incluido en este repositorio.

   Este repositorio contiene un bot de Discord escrito con discord.py (v2.x) que incluye múltiples "cogs" (módulos) para administración, divertimento, automaciones, manejo de canales de voz temporales, gestión de roles, tickets y más.

   ## Contenido del repositorio

   Principal:
   - `main.py` — Punto de entrada del bot y encargado de cargar los cogs y sincronizar los comandos slash.
   - `requirements.txt` — Dependencias necesarias (p. ej. `discord.py`, `python-dotenv`).
   - `README.md` — Este archivo.
   - `docker-compose.yml` — Opcional para correr servicios (p. ej. lavalink).

   Carpeta `cogs/`: módulos del bot. Los archivos presentes en este repo son:
   - `admin.py` — Comandos y utilidades de administración (kick, ban, permisos, etc.).
   - `ai.py` — Integraciones/automatizaciones relacionadas con IA (si está implementado).
   - `automations.py` — Automatizaciones basadas en mensajes, reacciones y roles (p. ej. presentaciones, manejos de boosts, triggers como "Down").
   - `fun.py` — Comandos de entretenimiento (dados, piedra-papel-tijera, música simple, etc.).
   - `iconos.py` — Publicación/gestión de iconos (paneles de reacciones para seleccionar iconos/roles).
   - `moderation.py` — Moderación adicional (logs, advertencias, historial).
   - `music_slash.py` — Comandos slash para música (requiere Lavalink o similar).
   - `personalvoice.py` — Gestión de canales de voz personales/temporales.
   - `poll.py` — Comandos para crear encuestas y votaciones.
   - `publish_icons_panel.py` — Publica paneles de selección de iconos/roles.
   - `selfroles.py` y `selfroles_colors.py` — Gestión de roles asignables por los propios usuarios.
   - `setup.py` — Asistentes/ayudas para configurar el bot en un servidor.
   - `syncfix.py` — Herramientas para sincronizar commands o arreglos de slash commands.
   - `tempvoice.py` — Implementación de canales de voz temporales (join-to-create) con control de propietario y permisos.
   - `tickets.py` — Sistema de tickets (crear, cerrar, logs).
   - `utility.py` — Comandos utilitarios (ping, server-info, user-info, etc.).

   Archivos de datos (`data/`): configuración y persistencia simple en JSON.

   ## Requisitos

   - Python 3.10+ recomendado.
   - `discord.py` (>=2.4.0) — para comandos slash y nuevas features.
   - `python-dotenv` — para cargar variables de entorno desde un archivo `.env`.

   Instalar dependencias:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -U -r requirements.txt
   ```

   ## Configuración (variables de entorno)

   El bot usa variables de entorno para el token y parámetros opcionales. Crea un `.env` en la raíz con al menos:

   ```
   DISCORD_TOKEN=tu_token_aqui
   GUILD_ID=123456789012345678   # Opcional: para sincronizar los slash commands en un servidor específico
   SYNC_ON_START=1               # 1 o 0 (sincronizar comandos al iniciar)
   SYNC_COOLDOWN_MIN=3           # Cooldown entre sincronizaciones
   ```

   Nota: Si planeas usar la funcionalidad de música (Lavalink), necesitarás desplegar un servidor Lavalink y configurar `lavalink/application.yml` o las credenciales necesarias. El proyecto incluye una carpeta `lavalink/` con un `application.yml` de ejemplo.

   Privileged Gateway Intents
   - Ve a Discord Developer Portal → tu aplicación → Bot → Privileged Gateway Intents y activa:
      - SERVER MEMBERS INTENT (necesario para eventos de miembros/roles)
      - MESSAGE CONTENT INTENT (necesario para leer mensajes en `automations.py` y triggers basados en contenido)

   ## Uso

   Inicia el bot:

   ```bash
   python main.py
   ```

   Si `GUILD_ID` está configurado y es un ID válido, el bot intentará sincronizar los comandos slash solo en ese servidor (ideal para desarrollo). Si no, sincronizará globalmente (puede tardar minutos en propagarse).

   ### Comandos y funcionalidades por cog (resumen)

   - `cogs.utility`:
      - `/ping` — Responde con latencia básica.
      - `/server-info` — Información del servidor.
      - `/user-info` — Información de un usuario (necesita intents de miembros).

   - `cogs.admin`:
      - Kick, ban, limpiar mensajes, comandos de moderación general.

   - `cogs.moderation`:
      - Logs, advertencias, acciones automáticas cuando se pierden roles de boost, etc.

   - `cogs.selfroles` / `selfroles_colors`:
      - Permite a los usuarios asignarse roles mediante reacciones o comandos.

   - `cogs.automations`:
      - Reacciones automáticas en canales de presentaciones.
      - Triggers basados en contenido (p. ej. detectar "Down").
      - Manejo automático cuando un usuario gana/pierde rol de boost.

   - `cogs.tempvoice` / `cogs.personalvoice`:
      - Join-to-create de canales de voz temporales.
      - Comandos para renombrar, cambiar límite, bloquear/ocultar, transferir propiedad, expulsar/banear de la sala, reclamar propiedad, limpiar canales vacíos.

   - `cogs.music_slash`:
      - Comandos slash para reproducir música mediante Lavalink (requerido servidor Lavalink y credenciales).

   - `cogs.poll`:
      - Crear encuestas y recoger votos mediante reacciones o componentes.

   - `cogs.tickets`:
      - Crear tickets (canales privados entre staff y usuario), cerrar tickets y mantener logs.

   - `cogs.iconos` / `publish_icons_panel`:
      - Publicar paneles de selección de iconos/roles con reacciones y atajos.

   - `cogs.ai`:
      - Integraciones con IA (chat, respuestas automáticas) si se configura.

   ## Desarrollo y despliegue

   - Ejecución en local: usar el virtualenv e iniciar `main.py`.
   - Docker / docker-compose: si quieres ejecutar un stack con Lavalink o servicios adicionales, revisa `docker-compose.yml` y la carpeta `lavalink/`. Ajusta puertos y secretos según tu entorno.

   Ejemplo mínimo con docker-compose (si tienes un servicio de lavalink en el compose):

   ```bash
   docker compose up -d
   ```

   y luego ejecutar el bot en tu entorno Python o empaquetarlo en una imagen.

   ## Archivos de datos

   La carpeta `data/` contiene JSON simples para persistencia:
   - `config.json` — Configuración del bot leída por `main.py`.
   - `birthdays.json`, `personal_channels.json`, `tempvoice.json`, `tickets.json` — Ejemplos y persistencia para features relacionadas.

   ## Troubleshooting (puntos comunes)

   - Error: "Falta DISCORD_TOKEN en .env" — Asegúrate de crear `.env` y definir `DISCORD_TOKEN`.
   - Slash commands no aparecen — Si sincronizas globalmente, puede tardar; para pruebas usa `GUILD_ID` para sincronizar inmediatamente en un servidor.
   - Permisos en intents — Activa los intents en el portal de Discord y vuelve a iniciar el bot.
   - Cogs que no cargan — Revisa la salida que imprime `main.py` al cargar extensiones; mostrará excepciones.

   ## Contribuir

   1. Abre un issue describiendo el cambio o bug.
   2. Crea una rama feature/bugfix.
   3. Añade pruebas o verifica localmente.
   4. Haz un PR hacia `main` con descripción y cambios.

   ## Licencia y autor

   Repositorio: `bot-riot-Friends` (owner: AlejandroVegaFullstackDev).

   Si necesitas que traduzca partes concretas, añada ejemplos de `.env` o documente un cog con más detalle, dime cuál y lo amplío.
