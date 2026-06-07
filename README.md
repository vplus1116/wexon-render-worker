# WEXON T1 Render Worker (RunPod Serverless)

Собирает рекламный ролик T1: сцены (картинка + озвучка Piper) → вертикальный
монтаж 1080×1920 (размытый фон + зум + субтитры + музыка) через ffmpeg →
загрузка в Cloudinary → возврат URL.

Текст (Qwen) и картинки (FLUX) генерятся отдельными RunPod-эндпоинтами — этот
воркер делает **озвучку + монтаж** (то, для чего нет готового эндпоинта).

## Как развернуть на RunPod (из этого репо)
1. RunPod Console → **Serverless** → **New Endpoint** → **Import from GitHub** (или
   Custom → Source: GitHub) → выбрать этот репозиторий.
2. Build context: корень репо (Dockerfile в корне). RunPod сам соберёт образ.
3. Worker: CPU-воркер достаточно (можно 2–4 vCPU). GPU не нужен для T1.
4. **Environment variables** добавить:
   - `CLOUDINARY_URL` = `cloudinary://<api_key>:<api_secret>@<cloud_name>`
     (или раздельно `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`)
5. Deploy → скопировать **Endpoint ID / URL** и положить в `.env` бэкенда как
   `RUNPOD_T1_ENDPOINT`.

## Формат запроса (RunPod /run или /runsync)
```json
{
  "input": {
    "lang": "ru",
    "scenes": [
      {"text": "Озвучка сцены 1", "image_url": "https://.../s1.png", "subtitle": "Сцена 1"},
      {"text": "Озвучка сцены 2", "image_url": "https://.../s2.png"}
    ],
    "music_url": "https://.../track.mp3"
  }
}
```
Ответ: `{"video_url": "<cloudinary>", "duration": 18.4, "scenes": 2}`

## Компоненты
- `handler.py` — RunPod-обработчик (TTS + загрузка картинок + монтаж + Cloudinary)
- `render_t1.py` — движок монтажа (ffmpeg)
- `Dockerfile` — ffmpeg + Piper + голоса (ru, en)
- `music/` — положить лицензионные треки (см. music/README.md)

## Языки / голоса
MVP: русский (`ru_RU-irina-medium`) и английский (`en_US-amy-medium`).
uk/es/it/zh временно маппятся (добавить native-голоса Piper позже в Dockerfile + handler).
