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
   source .venv/bin/activate
   pip install -U -r requirements.txt
   ```
2. Copia `.env.example` a `.env` y rellena **token** y **IDs** (ver cómo obtener IDs en Ajustes de Discord → Avanzado → modo Desarrollador).
3. Ejecuta:
   ```bash
   python main.py
   ```
4. Los *slash* aparecen **al instante** si pones `GUILD_ID`. Si no, la propagación global tarda unos minutos.

## Estructura
```
discord-bot-starter-es/
├─ cogs/
│  ├─ automations.py
│  ├─ admin.py
│  ├─ fun.py
│  ├─ poll.py
│  └─ utility.py
├─ data/
│  └─ birthdays.json (no usado aquí, solo de ejemplo)
├─ .env(.example)
├─ main.py
├─ requirements.txt
└─ README.md
```

---

## Temporary Voice Channels (Join‑to‑Create)
Configura uno o más **hubs** (IDs en `TEMPVOICE_HUB_IDS`). Cuando un usuario entra a un hub, el bot crea un canal temporal con nombre según `TEMPVOICE_NAME_TEMPLATE` (usa `{index}` y `{username}`), aplica límite `TEMPVOICE_DEFAULT_LIMIT`, mueve al usuario y lo marca como **propietario**.

Comandos disponibles (dentro del canal temporal):
- `/voice-rename <nombre>`
- `/voice-limit <n>`
- `/voice-lock` / `/voice-unlock`
- `/voice-hide` / `/voice-reveal`
- `/voice-kick <miembro>`
- `/voice-ban <miembro>` / `/voice-unban <miembro>`
- `/voice-transfer <miembro>` (pasa la propiedad)
- `/voice-owner` (muestra propietario)
- `/voice-claim` (reclama el canal si no hay dueño o pasó el candado)
- `/voice-clean` (borra canales temporales vacíos — admins)

El canal se borra automáticamente si queda vacío por `TEMPVOICE_KEEPALIVE_MIN` minutos.
# bot-riot-Friends
