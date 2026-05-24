"""
Apply CSV router to the FastAPI app.
Imported once at the bottom of app.py via: from web.app_csv_patch import apply_csv_routes
"""
from fastapi import FastAPI


def apply_csv_routes(app: FastAPI) -> None:
    from web.csv_routes import csv_router
    app.include_router(csv_router)
