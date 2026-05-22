from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from db.database import (
    init_db, get_user_by_email, create_user, get_or_create_oauth_user,
    get_user_by_id, update_user_settings
)
from server.auth import (
    hash_password, verify_password, create_token, get_current_user,
    get_google_auth_url, exchange_google_code,
    get_github_auth_url, exchange_github_code,
    GOOGLE_CLIENT_ID, GITHUB_CLIENT_ID, FRONTEND_URL
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/signup")
async def signup(body: dict):
    """Register a new user with email + password."""
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    name = body.get("name", "").strip()

    if not email or not password:
        raise HTTPException(400, "Email and password are required")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    SessionFactory = init_db()
    with SessionFactory() as session:
        existing = get_user_by_email(session, email)
        if existing:
            raise HTTPException(409, "An account with this email already exists")

        user = create_user(
            session, email=email, name=name,
            provider="email", hashed_password=hash_password(password),
        )
        token = create_token(user.id, user.email, user.name)
        return {
            "token": token,
            "user": {"id": user.id, "email": user.email, "name": user.name, "picture": user.picture},
        }

@router.post("/login")
async def login(body: dict):
    """Login with email + password."""
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        raise HTTPException(400, "Email and password are required")

    SessionFactory = init_db()
    with SessionFactory() as session:
        user = get_user_by_email(session, email)
        if not user or not user.hashed_password:
            raise HTTPException(401, "Invalid email or password")
        if not verify_password(password, user.hashed_password):
            raise HTTPException(401, "Invalid email or password")

        token = create_token(user.id, user.email, user.name)
        return {
            "token": token,
            "user": {"id": user.id, "email": user.email, "name": user.name, "picture": user.picture},
        }

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    SessionFactory = init_db()
    with SessionFactory() as session:
        user = get_user_by_email(session, current_user["email"])
        if not user:
            raise HTTPException(404, "User not found")
        return {
            "id": user.id, "email": user.email,
            "name": user.name, "picture": user.picture,
            "provider": user.provider,
            "has_openai": bool(user.openai_api_key),
            "has_gemini": bool(user.gemini_api_key),
            "preferred_model": user.preferred_model,
        }

@router.get("/google")
async def google_login(request: Request):
    """Redirect user to Google consent screen."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(501, "Google OAuth not configured")
    redirect_uri = str(request.url_for("google_callback"))
    return RedirectResponse(get_google_auth_url(redirect_uri))

@router.get("/google/callback")
async def google_callback(request: Request, code: str = Query(...)):
    """Handle Google OAuth callback."""
    redirect_uri = str(request.url_for("google_callback"))
    user_info = await exchange_google_code(code, redirect_uri)
    email = user_info.get("email", "")
    name = user_info.get("name", "")
    picture = user_info.get("picture", "")

    if not email:
        raise HTTPException(400, "Could not get email from Google")

    SessionFactory = init_db()
    with SessionFactory() as session:
        user = get_or_create_oauth_user(session, email, name, picture, "google")
        token = create_token(user.id, user.email, user.name)

    return RedirectResponse(f"{FRONTEND_URL}/?token={token}")

@router.get("/github")
async def github_login(request: Request):
    """Redirect user to GitHub consent screen."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(501, "GitHub OAuth not configured")
    redirect_uri = str(request.url_for("github_callback"))
    return RedirectResponse(get_github_auth_url(redirect_uri))

@router.get("/github/callback")
async def github_callback(request: Request, code: str = Query(...)):
    """Handle GitHub OAuth callback."""
    redirect_uri = str(request.url_for("github_callback"))
    user_info = await exchange_github_code(code, redirect_uri)
    email = user_info.get("email", "")
    name = user_info.get("name", "")
    picture = user_info.get("picture", "")

    if not email:
        raise HTTPException(400, "Could not get email from GitHub")

    SessionFactory = init_db()
    with SessionFactory() as session:
        user = get_or_create_oauth_user(session, email, name, picture, "github")
        token = create_token(user.id, user.email, user.name)

    return RedirectResponse(f"{FRONTEND_URL}/?token={token}")

@router.get("/providers")
async def auth_providers():
    """Return which OAuth providers are configured."""
    return {
        "google": bool(GOOGLE_CLIENT_ID),
        "github": bool(GITHUB_CLIENT_ID),
    }

# Also move user settings to a separate router or include here. 
# Let's put settings in user.py
