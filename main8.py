import asyncio
import logging
import sqlite3
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL")

if not BOT_TOKEN:
    raise ValueError("Токен бота не найден! Проверьте файл .env")
if not WEB_APP_URL:
    raise ValueError("Ссылка на Web App не найдена! Проверьте файл .env")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# === БАЗА ДАННЫХ (УМНАЯ МИГРАЦИЯ) ===
def init_db() -> None:
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()

        # 1. Создаем таблицу, если ее вообще нет
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            )
        """)

        # 2. Пытаемся добавить новую колонку.
        # Если это старая база - колонка добавится. Если новая - ошибка игнорируется.
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN high_score INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует, все отлично

        conn.commit()


def update_high_score(user_id: int, username: str, score: int) -> None:
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, high_score) 
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
            username = excluded.username,
            high_score = MAX(users.high_score, excluded.high_score)
        """, (user_id, username, score))
        conn.commit()


def get_top_players() -> list[dict]:
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, high_score FROM users ORDER BY high_score DESC LIMIT 10")
        rows = cursor.fetchall()
        return [{"username": row[0], "score": row[1]} for row in rows if row[1] > 0]


def get_user_high_score(user_id: int) -> int:
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT high_score FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else 0


# === HTML ШАБЛОН ИГРЫ ===
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Purble Cakes Mini App</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #f7d5e6; margin: 0; padding: 10px; display: flex; flex-direction: column; align-items: center; overflow: hidden; }
        .tabs { display: flex; width: 100%; max-width: 400px; margin-bottom: 10px; border-radius: 8px; overflow: hidden; background: #ddd; }
        .tab-btn { flex: 1; padding: 10px; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; background: transparent; }
        .tab-btn.active { background: #333; color: white; }
        .tab-content { display: none; width: 100%; max-width: 400px; flex-direction: column; align-items: center; }
        .tab-content.active { display: flex; }
        .header { display: flex; justify-content: space-between; align-items: center; width: 100%; font-weight: bold; color: #333; margin-bottom: 10px; }
        .header-title { font-size: 18px; }
        .score-box { text-align: right; }
        .current-score { font-size: 18px; }
        .best-score { font-size: 12px; color: #666; margin-top: -2px; }
        .tv-screen { background-color: #333; border: 4px solid #777; border-radius: 8px; width: 90px; height: 130px; display: flex; flex-direction: column-reverse; align-items: center; padding: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
        .tv-placeholder { color: white; font-size: 40px; margin-top: 30px; opacity: 0.5; }
        .conveyor-container { background-color: #444; width: 100%; height: 150px; margin-top: 15px; border-radius: 8px; position: relative; box-shadow: inset 0 5px 10px rgba(0,0,0,0.5); overflow: hidden; border-top: 5px solid #222; border-bottom: 5px solid #222; }
        .moving-cake { position: absolute; bottom: 5px; left: 0%; width: 90px; display: flex; flex-direction: column-reverse; align-items: center; }
        .layer { width: 70px; height: 15px; border: 1px solid rgba(0,0,0,0.3); border-radius: 3px; }
        .pan { width: 85px; height: 8px; background-color: #ccc; border-radius: 2px; }
        .batter-choc { background-color: #4a2e15; height: 20px;}
        .batter-straw { background-color: #ff66a3; height: 20px;}
        .batter-plain { background-color: #fce08b; height: 20px;}
        .filling-jam { background-color: #800080; width: 65px; height: 6px; }
        .filling-choc { background-color: #2b180a; width: 65px; height: 6px; }
        .cream-red { background-color: #d92525; height: 15px; }
        .cream-green { background-color: #3cc95c; height: 15px; }
        .cream-white { background-color: #ffffff; height: 15px; }
        .deco { font-size: 24px; line-height: 24px; height: 24px; margin-bottom: -5px; z-index: 2; }
        .controls-wrapper { width: 100%; margin-top: 15px; min-height: 140px; display: flex; flex-direction: column; justify-content: center; }
        .controls-play { display: none; flex-direction: column; gap: 8px; width: 100%; }
        .controls-menu { display: flex; flex-direction: column; align-items: center; width: 100%; }
        .control-row { display: flex; justify-content: center; gap: 5px; }
        button { flex: 1; padding: 8px 4px; font-size: 12px; font-weight: bold; border: none; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); cursor: pointer; transition: 0.1s; }
        button:active { transform: translateY(2px); box-shadow: none; }
        .btn-main-action { background-color: #3cc95c; color: white; font-size: 18px; padding: 15px 30px; border-radius: 10px; width: 80%; max-width: 250px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .btn-main-action:active { transform: translateY(3px); box-shadow: 0 1px 2px rgba(0,0,0,0.3); }
        .status { margin-top: 10px; font-weight: bold; font-size: 16px; height: 20px; text-align: center;}
        .leaderboard-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .leaderboard-table th, .leaderboard-table td { padding: 10px; border-bottom: 1px solid #ccc; text-align: left; }
        .leaderboard-table th { background-color: #eee; }
    </style>
</head>
<body>

    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('game')">Фабрика</button>
        <button class="tab-btn" onclick="switchTab('leaderboard')">Рекорды</button>
    </div>

    <div id="tab-game" class="tab-content active">
        <div class="header">
            <div class="header-title">Заказ:</div>
            <div class="score-box">
                <div class="current-score" id="score-display">Счет: 0</div>
                <div class="best-score" id="best-score-display">Рекорд: 0</div>
            </div>
        </div>

        <div class="tv-screen" id="target-cake">
            <div class="tv-placeholder">?</div>
        </div>

        <div class="status" id="status-text">Готов к работе?</div>

        <div class="conveyor-container">
            <div class="moving-cake" id="moving-cake"></div>
        </div>

        <div class="controls-wrapper">
            <div class="controls-menu" id="controls-menu">
                <button class="btn-main-action" id="btn-start" onclick="startGame()">▶ Начать игру</button>
            </div>

            <div class="controls-play" id="controls-play">
                <div class="control-row">
                    <button style="background-color: #fce08b;" onclick="addLayer('batter-plain')">Обычное</button>
                    <button style="background-color: #ff66a3;" onclick="addLayer('batter-straw')">Клубнич.</button>
                    <button style="background-color: #4a2e15; color: white;" onclick="addLayer('batter-choc')">Шоко.</button>
                </div>
                <div class="control-row">
                    <button style="background-color: #800080; color: white;" onclick="addLayer('filling-jam')">Джем</button>
                    <button style="background-color: #2b180a; color: white;" onclick="addLayer('filling-choc')">Шоко-паста</button>
                </div>
                <div class="control-row">
                    <button style="background-color: #fff; border: 1px solid #ccc;" onclick="addLayer('cream-white')">Бел. крем</button>
                    <button style="background-color: #d92525; color: white;" onclick="addLayer('cream-red')">Красный</button>
                    <button style="background-color: #3cc95c;" onclick="addLayer('cream-green')">Зеленый</button>
                </div>
                <div class="control-row">
                    <button style="background-color: #a3e4d7;" onclick="addDecoration('🍒')">🍒 Вишня</button>
                    <button style="background-color: #a3e4d7;" onclick="addDecoration('🍀')">🍀 Клевер</button>
                    <button style="background-color: #ff7675; color: white;" onclick="trashCake()">🗑 Сброс</button>
                </div>
            </div>
        </div>
    </div>

    <div id="tab-leaderboard" class="tab-content">
        <h2>Топ 10 Кондитеров</h2>
        <table class="leaderboard-table">
            <thead><tr><th>Игрок</th><th>Счет</th></tr></thead>
            <tbody id="leaderboard-body">
                [[LEADERBOARD_ROWS]]
            </tbody>
        </table>
    </div>

    <script>
        let tg = window.Telegram.WebApp;
        tg.expand();

        function safeVibrate(type) {
            try {
                if (tg && tg.HapticFeedback) {
                    if (['light', 'medium', 'heavy', 'rigid', 'soft'].includes(type)) {
                        tg.HapticFeedback.impactOccurred(type);
                    } else {
                        tg.HapticFeedback.notificationOccurred(type);
                    }
                }
            } catch (err) {
                console.log("Вибрация не поддерживается");
            }
        }

        const API_HEADERS = {
            'Content-Type': 'application/json',
            'Bypass-Tunnel-Reminder': 'true'
        };

        const batters = ['batter-plain', 'batter-straw', 'batter-choc'];
        const fillings = ['filling-jam', 'filling-choc'];
        const creams = ['cream-white', 'cream-red', 'cream-green'];
        const decos = ['🍒', '🍀'];

        let targetRecipe = [];
        let currentCake = [];
        let score = 0;
        let personalBest = 0;
        let position = -10;
        const BASE_SPEED = 0.08;
        let speed = BASE_SPEED;
        const MAX_SPEED = 0.35;
        let animationId = null;
        let isProcessing = false;
        let isPlaying = false;

        async function loadPersonalBest() {
            const user = tg.initDataUnsafe?.user;
            if (user) {
                try {
                    const response = await fetch(`/api/user_score?user_id=${user.id}`, { headers: API_HEADERS });
                    const text = await response.text();
                    const data = JSON.parse(text); 
                    personalBest = data.score || 0;
                    document.getElementById('best-score-display').innerText = `Рекорд: ${personalBest}`;
                } catch (err) {
                    console.log("Загрузка рекорда заблокирована");
                }
            }
        }

        function switchTab(tabId) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

            event.target.classList.add('active');
            document.getElementById(`tab-${tabId}`).classList.add('active');
        }

        function startGame() {
            safeVibrate('heavy');
            document.getElementById('controls-menu').style.display = 'none';
            document.getElementById('controls-play').style.display = 'flex';

            score = 0;
            speed = BASE_SPEED;
            document.getElementById('score-display').innerText = `Счет: 0`;
            setStatus("Собери 5 слоев!", "#333");

            isPlaying = true;
            isProcessing = false;

            position = -10;
            currentCake = ['pan'];
            generateOrder();
            renderCake('moving-cake', currentCake);

            if (animationId) cancelAnimationFrame(animationId);
            gameLoop();
        }

        function stopGame(reason) {
            isPlaying = false;
            if (animationId) cancelAnimationFrame(animationId);

            setStatus(reason + " Игра окончена!", "red");
            safeVibrate('error');
            saveScoreToServer();

            document.getElementById('controls-play').style.display = 'none';
            document.getElementById('controls-menu').style.display = 'flex';
            document.getElementById('btn-start').innerText = "🔄 Начать заново";
            document.getElementById('btn-start').style.backgroundColor = "#ff9f43";

            document.getElementById('target-cake').innerHTML = '<div class="tv-placeholder">X</div>';
            document.getElementById('moving-cake').innerHTML = '';
        }

        function generateOrder() {
            const randomBatter = batters[Math.floor(Math.random() * batters.length)];
            const randomFilling = fillings[Math.floor(Math.random() * fillings.length)];
            const randomCream = creams[Math.floor(Math.random() * creams.length)];
            const randomDeco = decos[Math.floor(Math.random() * decos.length)];

            targetRecipe = ['pan', randomBatter, randomFilling, randomCream, randomDeco];
            renderCake('target-cake', targetRecipe);
        }

        function renderCake(containerId, recipeArray) {
            const container = document.getElementById(containerId);
            container.innerHTML = '';
            recipeArray.forEach(item => {
                let div = document.createElement('div');
                if (decos.includes(item)) { div.className = 'deco'; div.innerText = item; }
                else { div.className = item === 'pan' ? 'pan' : `layer ${item}`; }
                container.appendChild(div);
            });
        }

        function addLayer(layerClass) {
            if (isProcessing || !isPlaying) return;
            currentCake.push(layerClass);
            renderCake('moving-cake', currentCake);
            safeVibrate('light');
        }

        function addDecoration(emoji) {
            if (isProcessing || !isPlaying) return;
            currentCake.push(emoji);
            renderCake('moving-cake', currentCake);
            safeVibrate('medium');
            checkCake();
        }

        function trashCake() {
            if (isProcessing || !isPlaying) return;
            currentCake = ['pan'];
            renderCake('moving-cake', currentCake);
            safeVibrate('warning');
        }

        function saveScoreToServer() {
            const user = tg.initDataUnsafe?.user;
            if (user && score > 0) {
                fetch(`/api/score`, {
                    method: 'POST',
                    headers: API_HEADERS,
                    body: JSON.stringify({
                        user_id: user.id,
                        username: user.username || user.first_name,
                        score: score
                    })
                }).catch(err => console.log("Отправка счета заблокирована:", err));
            }
        }

        function checkCake() {
            const isWin = currentCake.length === targetRecipe.length && currentCake.every((val, index) => val === targetRecipe[index]);

            if (isWin) {
                setStatus("Идеально!", "green");
                score++;
                document.getElementById('score-display').innerText = `Счет: ${score}`;

                if (score > personalBest) {
                    personalBest = score;
                    document.getElementById('best-score-display').innerText = `Рекорд: ${personalBest}`;
                }

                safeVibrate('success');
                if (speed < MAX_SPEED) speed += 0.005;

                resetRound();
            } else {
                stopGame("Неверный рецепт!");
            }
        }

        function gameLoop() {
            if (!isPlaying) return;

            if (!isProcessing) {
                position += speed;
                document.getElementById('moving-cake').style.left = `${position}%`;

                if (position > 100) {
                    stopGame("Не успел!");
                    return;
                }
            }
            animationId = requestAnimationFrame(gameLoop);
        }

        function resetRound() {
            isProcessing = true;
            setTimeout(() => {
                if (!isPlaying) return;
                position = -10;
                currentCake = ['pan'];
                generateOrder();
                renderCake('moving-cake', currentCake);
                setStatus("Новый заказ!", "#333");
                isProcessing = false;
            }, 1000);
        }

        function setStatus(text, color) {
            const statusEl = document.getElementById('status-text');
            statusEl.innerText = text;
            statusEl.style.color = color;
        }

        loadPersonalBest();
    </script>
</body>
</html>
"""


# === ПРОФЕССИОНАЛЬНЫЙ ОБХОД CORS ===
@web.middleware
async def cors_middleware(request: web.Request, handler) -> web.Response:
    if request.method == "OPTIONS":
        return web.Response(headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Bypass-Tunnel-Reminder",
        })

    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


# === ХЭНДЛЕРЫ БОТА ===
@dp.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎂 Играть в Comfy Cakes", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    await message.answer("Добро пожаловать на кондитерскую фабрику!\nСоревнуйся с друзьями!", reply_markup=keyboard)


# === AIOHTTP ВЕБ-СЕРВЕР ===
async def handle_index(request: web.Request) -> web.Response:
    """Генерирует HTML и сразу встраивает в него актуальную таблицу лидеров."""

    # 1. Получаем игроков из базы
    top_players = get_top_players()

    # 2. Генерируем HTML-код для таблицы
    if not top_players:
        leaderboard_html = '<tr><td colspan="2" style="text-align: center;">Пока нет рекордов! Сыграй первым!</td></tr>'
    else:
        leaderboard_html = ""
        for index, player in enumerate(top_players):
            medal = '🥇 ' if index == 0 else '🥈 ' if index == 1 else '🥉 ' if index == 2 else ''
            leaderboard_html += f"<tr><td>{medal}{player['username']}</td><td>{player['score']}</td></tr>"

    # 3. Вставляем таблицу в наш большой HTML-шаблон (Используем надежный маркер)
    final_html = HTML_TEMPLATE.replace('[[LEADERBOARD_ROWS]]', leaderboard_html)

    # 4. Отправляем пользователю готовую страницу
    return web.Response(text=final_html, content_type='text/html')


async def handle_submit_score(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        user_id = data.get('user_id')
        username = data.get('username') or f"User_{user_id}"
        score = data.get('score', 0)

        if user_id:
            update_high_score(user_id, username, score)
        return web.json_response({"status": "success"})
    except Exception as e:
        logger.error(f"Ошибка сохранения счета: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=400)


async def handle_get_user_score(request: web.Request) -> web.Response:
    try:
        user_id = int(request.query.get('user_id', 0))
        if not user_id:
            return web.json_response({"score": 0})
        score = get_user_high_score(user_id)
        return web.json_response({"score": score})
    except ValueError:
        return web.json_response({"score": 0})


async def start_web_server() -> None:
    app = web.Application(middlewares=[cors_middleware])

    app.router.add_get('/', handle_index)
    app.router.add_post('/api/score', handle_submit_score)
    app.router.add_get('/api/user_score', handle_get_user_score)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    logger.info("Веб-сервер запущен на http://localhost:8080")


# === ЗАПУСК ===
async def main() -> None:
    init_db()
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())