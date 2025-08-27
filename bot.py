import os
import asyncio
import discord
import requests
import sqlite3
from discord.ext import tasks, commands
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
CANVAS_URL = os.getenv("CANVAS_URL")
CANVAS_TOKEN = os.getenv("CANVAS_TOKEN")
CANVAS_COURSE_ID = int(os.getenv("CANVAS_COURSE_ID"))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

HEADERS = {"Authorization": f"Bearer {CANVAS_TOKEN}"}

seen_assignments = set()
seen_announcements = set()
seen_quizzes = set()


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
            # some endpoints return a dict
            results.append(data)

        # pagination from the Link header
        links = requests.utils.parse_header_links(r.headers.get("Link", ""))
        next_url = None
        for link in links:
            if link.get("rel") == "next":
                next_url = link.get("url")
        url = next_url

    return results


@tasks.loop(minutes=5)
async def check_canvas():
    channel = bot.get_channel(DISCORD_CHANNEL_ID)

    print("\n📌 Checking Canvas for updates...")

    # --- Assignments ---
    assignments = fetch_canvas("assignments")
    print(f"Found {len(assignments)} assignments")
    for assignment in assignments:
        print(f" - [Assignment] {assignment['name']} (ID: {assignment['id']})")
        if assignment["id"] not in seen_assignments:
            seen_assignments.add(assignment["id"])
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
        if ann["id"] not in seen_announcements:
            seen_announcements.add(ann["id"])
            msg = ann.get("message", "No details")
            if msg and len(msg) > 200:
                msg = msg[:200] + "..."
            await send_embed(
                channel,
                f"📢 New Announcement: {ann['title']}",
                msg,
                ann["html_url"],
                discord.Color.orange()
            )

    # --- Quizzes ---
    quizzes = fetch_canvas("quizzes")
    print(f"Found {len(quizzes)} quizzes")
    for quiz in quizzes:
        print(f" - [Quiz] {quiz['title']} (ID: {quiz['id']})")
        if quiz["id"] not in seen_quizzes:
            seen_quizzes.add(quiz["id"])
            await send_embed(
                channel,
                f"❓ New Quiz: {quiz['title']}",
                f"Due: {quiz['due_at']}" if quiz["due_at"] else "No due date",
                quiz["html_url"],
                discord.Color.red()
            )


@bot.event
async def on_ready():
    print(f"\n✅ Logged in as {bot.user}")
    print("🔄 Initializing Canvas check...")
    check_canvas.start()


async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)


asyncio.run(main())
