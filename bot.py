import os
import asyncio
import discord # type: ignore
import requests
import aiosqlite # type: ignore
from discord.ext import tasks, commands # type: ignore
from dotenv import load_dotenv # type: ignore

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
CANVAS_URL = os.getenv("CANVAS_URL")
CANVAS_TOKEN = os.getenv("CANVAS_TOKEN")
CANVAS_COURSE_ID = int(os.getenv("CANVAS_COURSE_ID"))

tables = {
    'assignments': """
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY
        );
    """,
    'announcements': """
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY
        );
    """,
    'quizzes': """
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY
        );
    """
}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

HEADERS = {"Authorization": f"Bearer {CANVAS_TOKEN}"}


async def send_embed(channel, title, description, url, color=discord.Color.blue()):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.add_field(name="Link", value=f"[Click here]({url})", inline=False)
    await channel.send(embed=embed)


def fetch_canvas(endpoint):
    url = f"{CANVAS_URL}/api/v1/courses/{CANVAS_COURSE_ID}/{endpoint}"
    results = []

    while url:
        r = requests.get(url, headers=HEADERS)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            results.append(data)

        # pagination from the Link header
        links = requests.utils.parse_header_links(r.headers.get("Link", ""))
        next_url = None
        for link in links:
            if link.get("rel") == "next":
                next_url = link.get("url")
        url = next_url

    return results


async def id_exists(db, table, post_id):
    async with db.execute(f"SELECT 1 FROM {table} WHERE id = ?", (post_id,)) as cursor:
        row = await cursor.fetchone()
        return row is not None


async def add_id(db, table, post_id):
    await db.execute(f"INSERT INTO {table} (id) VALUES (?)", (post_id,))


@tasks.loop(minutes=5)
async def check_canvas():
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if channel is None:
        print("⚠️ Channel not found!")
        return

    print("\n📌 Checking Canvas for updates...")

    async with aiosqlite.connect('posts.db') as db:
        # --- Assignments ---
        assignments = fetch_canvas("assignments")
        print(f"Found {len(assignments)} assignments")

        for assignment in assignments:
            print(f" - [Assignment] {assignment['name']} (ID: {assignment['id']})")
            if not await id_exists(db, "assignments", assignment["id"]):
                await add_id(db, "assignments", assignment["id"])
                await db.commit()
                await send_embed(
                    channel,
                    f"📝 New Assignment: {assignment['name']}",
                    f"Due: {assignment['due_at']}" if assignment["due_at"] else "No due date",
                    assignment["html_url"],
                    discord.Color.green()
                )

        # --- Announcements ---
        announcements = fetch_canvas("discussion_topics?only_announcements=true")
        print(f"Found {len(announcements)} announcements")
        for ann in announcements:
            print(f" - [Announcement] {ann['title']} (ID: {ann['id']})")
            if not await id_exists(db, "announcements", ann["id"]):
                await add_id(db, "announcements", ann["id"])
                await db.commit()
                msg = ann.get("message", "No details")
                if msg and len(msg) > 200:
                    msg = msg[:200] + "..."
                await send_embed(
                    channel,
                    f"📢 New Announcement: {ann['title']}",
                    msg,
                    ann["html_url"],
                    discord.Color.red()
                )

        # --- Quizzes ---
        quizzes = fetch_canvas("quizzes")
        print(f"Found {len(quizzes)} quizzes")
        for quiz in quizzes:
            print(f" - [Quiz] {quiz['title']} (ID: {quiz['id']})")
            if not await id_exists(db, "quizzes", quiz["id"]):
                await add_id(db, "quizzes", quiz["id"])
                await db.commit()
                await send_embed(
                    channel,
                    f"❓ New Quiz: {quiz['title']}",
                    f"Due: {quiz['due_at']}" if quiz["due_at"] else "No due date",
                    quiz["html_url"],
                    discord.Color.blue()
                )


async def check_and_create_tables():
    async with aiosqlite.connect('posts.db') as db:
        # Check which tables exist
        async with db.execute(f"""
            SELECT name 
            FROM sqlite_master 
            WHERE type = 'table' 
            AND name IN (?, ?, ?);
        """, tuple(tables.keys())) as cursor:
            existing = {row[0] async for row in cursor}

        missing_tables = set(tables.keys()) - existing

        for table in missing_tables:
            await db.execute(tables[table])
            print(f"Created missing table: {table}")

        await db.commit()
        return len(missing_tables) == 0


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print("🔄 Initializing Canvas check...")
    await check_and_create_tables()
    check_canvas.start()


async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN, log_handler=None)


asyncio.run(main())
