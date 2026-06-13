import os
from flask import Flask, render_template, redirect, request, session, Response, jsonify
import requests
from dotenv import load_dotenv
from db import get_bot_token, get_db
from bson.objectid import ObjectId
from flask import abort

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "make_up_a_random_string_here")

# Force Flask to use secure cookies for HTTPS (Railway)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Discord OAuth2 Config
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
BOT_TOKEN = get_bot_token()

# Connect to MongoDB (shared singleton with the bot)
db = get_db()


@app.route("/")
def index():
    return render_template("index.html", client_id=CLIENT_ID, redirect_uri=REDIRECT_URI)


@app.route("/login")
def login():
    return redirect(
        f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds"
    )


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect("/")

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": "identify guilds",
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DashboardBot/1.0",
    }

    response = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
    tokens = response.json()

    if "access_token" not in tokens:
        return redirect("/")

    session["access_token"] = tokens["access_token"]

    guild_response = requests.get(
        "https://discord.com/api/users/@me/guilds",
        headers={"Authorization": f"Bearer {session['access_token']}", "User-Agent": "DashboardBot/1.0"},
    )
    guilds = guild_response.json()

    if not isinstance(guilds, list):
        return redirect("/")

    manageable_guilds = [
        g
        for g in guilds
        if (int(g.get("permissions", 0)) & 0x8) == 0x8 or (int(g.get("permissions", 0)) & 0x20) == 0x20
    ]
    session["guilds"] = manageable_guilds
    return redirect("/dashboard")


@app.route("/dashboard")
def dashboard():
    if "access_token" not in session:
        return redirect("/")
    return render_template("dashboard.html", guilds=session.get("guilds", []))


@app.route("/transcripts")
def transcripts():
    """List all transcripts for the user's guilds."""
    if "access_token" not in session:
        return redirect("/")

    guilds = session.get("guilds", [])

    transcripts_by_guild = {}
    for guild in guilds:
        guild_id = int(guild["id"])
        guild_transcripts = list(db["transcripts"].find({"guild_id": guild_id}).sort("closed_at", -1).limit(50))

        if guild_transcripts:
            transcripts_by_guild[guild["name"]] = {"id": guild_id, "transcripts": guild_transcripts}

    return render_template("transcripts_list.html", transcripts_by_guild=transcripts_by_guild)


@app.route("/transcripts/<transcript_id>")
def view_transcript(transcript_id):
    """View a specific HTML transcript."""
    if "access_token" not in session:
        return redirect("/")

    try:
        obj_id = ObjectId(transcript_id)
    except:
        abort(404)

    transcript = db["transcripts"].find_one({"_id": obj_id})
    if not transcript:
        abort(404)

    guilds = session.get("guilds", [])
    user_guild_ids = [int(g["id"]) for g in guilds]

    if transcript["guild_id"] not in user_guild_ids:
        abort(403)

    return transcript["html_content"]


@app.route("/transcripts/<transcript_id>/raw")
def view_transcript_raw(transcript_id):
    """Download raw HTML transcript."""
    if "access_token" not in session:
        return redirect("/")

    try:
        obj_id = ObjectId(transcript_id)
    except:
        abort(404)

    transcript = db["transcripts"].find_one({"_id": obj_id})
    if not transcript:
        abort(404)

    guilds = session.get("guilds", [])
    user_guild_ids = [int(g["id"]) for g in guilds]

    if transcript["guild_id"] not in user_guild_ids:
        abort(403)

    response = Response(transcript["html_content"], mimetype="text/html")
    response.headers["Content-Disposition"] = f"attachment; filename=transcript-{transcript['channel_name']}.html"
    return response


@app.route("/dashboard/<int:guild_id>/commands", methods=["GET", "POST"])
def commands_dashboard(guild_id):
    """Command permissions management page."""
    if "access_token" not in session:
        return redirect("/")
    
    # Handle POST request (saving permissions)
    if request.method == "POST":
        form_type = request.form.get("form_type")
        
        if form_type == "save_cmd_perms":
            print(f"=" * 50)
            print(f"📝 SAVING COMMAND PERMISSIONS for guild {guild_id}")
            print(f"=" * 50)
            
            try:
                # Track what we saved
                saved_count = 0
                deleted_count = 0
                
                # Process each key in the form
                for key in request.form.keys():
                    if key.startswith("has_cmd_"):
                        # Get the command name (remove the prefix)
                        command_name = key[8:]  # "has_cmd_" is 8 characters
                        print(f"\n📌 Processing command: {command_name}")
                        
                        # Get all roles for this command
                        roles = request.form.getlist(f"cmd_{command_name}")
                        # Filter out empty strings and strip whitespace
                        roles = [r.strip() for r in roles if r and r.strip()]
                        
                        print(f"   Roles to save: {roles}")
                        
                        if roles:
                            # Save to database
                            db["command_perms"].update_one(
                                {"guild_id": guild_id, "command_name": command_name},
                                {"$set": {"roles": roles}},
                                upsert=True
                            )
                            saved_count += 1
                            print(f"   ✅ Saved {len(roles)} role(s) for /{command_name}")
                        else:
                            # Delete if no roles
                            result = db["command_perms"].delete_one({"guild_id": guild_id, "command_name": command_name})
                            if result.deleted_count > 0:
                                deleted_count += 1
                                print(f"   🗑️ Deleted permissions for /{command_name}")
                            else:
                                print(f"   ℹ️ No existing permissions for /{command_name}")
                
                print(f"\n✅ Summary: Saved {saved_count} commands, Deleted {deleted_count} commands")
                print(f"=" * 50)
                
                # Return JSON response
                return jsonify({
                    "success": True, 
                    "message": f"Saved {saved_count} command permissions",
                    "saved": saved_count,
                    "deleted": deleted_count
                })
                
            except Exception as e:
                print(f"❌ Error saving permissions: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({"success": False, "error": str(e)})
    
    # GET request - display the page
    if not BOT_TOKEN:
        return "<h1>Error: Discord bot token missing!</h1>", 500
    
    bot_headers = {"Authorization": f"Bot {BOT_TOKEN}", "User-Agent": "DashboardBot/1.0"}
    
    # Fetch Roles
    roles_res = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=bot_headers)
    roles = roles_res.json() if roles_res.status_code == 200 else []
    roles = [r for r in roles if r["name"] != "@everyone" and not r["managed"]]
    
    # Fetch saved command permissions
    command_perms = {}
    for doc in db["command_perms"].find({"guild_id": guild_id}):
        command_perms[doc["command_name"]] = doc["roles"]
    
    print(f"\n📋 LOADED COMMAND PERMISSIONS for guild {guild_id}:")
    for cmd, roles in command_perms.items():
        print(f"   /{cmd}: {roles}")
    
    guild_name = "Unknown Server"
    for g in session.get("guilds", []):
        if int(g["id"]) == guild_id:
            guild_name = g["name"]
            break
    
    settings = {"command_perms": command_perms}
    
    return render_template("commands.html", guild_id=guild_id, guild_name=guild_name, roles=roles, settings=settings)


@app.route("/dashboard/<int:guild_id>/commands", methods=["GET", "POST"])
def commands_dashboard(guild_id):
    """Command permissions management page."""
    if "access_token" not in session:
        return redirect("/")
    
    # Handle POST request (saving permissions)
    if request.method == "POST":
        form_type = request.form.get("form_type")
        
        if form_type == "save_cmd_perms":
            print(f"📝 Saving command permissions for guild {guild_id}")
            print(f"📝 Form data: {dict(request.form)}")
            
            try:
                # Process each command
                for key in request.form.keys():
                    if key.startswith("has_cmd_"):
                        command_name = key[9:]  # Remove "has_cmd_" prefix
                        roles = request.form.getlist(f"cmd_{command_name}")
                        
                        # Filter out empty strings
                        roles = [r for r in roles if r and r.strip()]
                        
                        if roles:
                            # Save to database
                            db["command_perms"].update_one(
                                {"guild_id": guild_id, "command_name": command_name},
                                {"$set": {"roles": roles}},
                                upsert=True
                            )
                            print(f"✅ Saved perms for {command_name}: {roles}")
                        else:
                            # Delete if no roles
                            result = db["command_perms"].delete_one({"guild_id": guild_id, "command_name": command_name})
                            if result.deleted_count > 0:
                                print(f"🗑️ Deleted perms for {command_name}")
                            else:
                                print(f"ℹ️ No existing perms for {command_name} to delete")
                
                # Return JSON response for AJAX requests
                return jsonify({"success": True, "message": "Permissions saved successfully"})
                
            except Exception as e:
                print(f"❌ Error saving permissions: {e}")
                return jsonify({"success": False, "error": str(e)})
    
    # GET request - display the page
    if not BOT_TOKEN:
        return "<h1>Error: Discord bot token missing!</h1>", 500
    
    bot_headers = {"Authorization": f"Bot {BOT_TOKEN}", "User-Agent": "DashboardBot/1.0"}
    
    # Fetch Roles
    roles_res = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=bot_headers)
    roles = roles_res.json() if roles_res.status_code == 200 else []
    roles = [r for r in roles if r["name"] != "@everyone" and not r["managed"]]
    
    # Fetch saved command permissions
    command_perms = {}
    for doc in db["command_perms"].find({"guild_id": guild_id}):
        command_perms[doc["command_name"]] = doc["roles"]
    
    print(f"📋 Loaded command perms for guild {guild_id}: {command_perms}")
    
    guild_name = "Unknown Server"
    for g in session.get("guilds", []):
        if int(g["id"]) == guild_id:
            guild_name = g["name"]
            break
    
    settings = {"command_perms": command_perms}
    
    return render_template("commands.html", guild_id=guild_id, guild_name=guild_name, roles=roles, settings=settings)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))