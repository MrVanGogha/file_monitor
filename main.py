from fastapi import FastAPI

from app.server import create_app


app: FastAPI = create_app()


def main():
    # Optional CLI entrypoint; prefer `uv run uvicorn main:app --reload`
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
