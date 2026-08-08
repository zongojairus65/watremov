"""
API FastAPI - Watermark Remover
Déploiement : Render (Docker)
Frontend : Vercel (Next.js) - appelle cette API via fetch()
"""

import os
import uuid
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from watermark_remover import remove_watermark_fixed

app = FastAPI(title="Watermark Remover API")

# CORS : autorise ton frontend Vercel à appeler cette API
# Remplace "*" par ton domaine Vercel exact en prod (ex: https://ton-app.vercel.app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE_DIR = Path("/tmp/watermark_jobs")
STORAGE_DIR.mkdir(exist_ok=True)

# Suivi en mémoire des jobs (simple, suffisant pour un usage modéré)
# Pour de la prod à plus grande échelle : remplacer par Redis
jobs = {}


def process_video(job_id: str, input_path: str, x: int, y: int, w: int, h: int,
                   method: str, radius: int):
    output_path = str(STORAGE_DIR / f"{job_id}_output.mp4")
    try:
        jobs[job_id]["status"] = "processing"
        remove_watermark_fixed(
            input_path, output_path,
            x, y, w, h,
            inpaint_radius=radius,
            method=method
        )
        jobs[job_id]["status"] = "done"
        jobs[job_id]["output_path"] = output_path
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
    finally:
        # Nettoyage du fichier d'entrée
        if os.path.exists(input_path):
            os.remove(input_path)


@app.post("/remove-watermark")
async def create_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    x: int = Form(...),
    y: int = Form(...),
    w: int = Form(...),
    h: int = Form(...),
    method: str = Form("ns"),
    radius: int = Form(4),
):
    """
    Reçoit une vidéo + coordonnées du watermark, lance le traitement en fond.
    Retourne un job_id à utiliser pour vérifier le statut.
    """
    if method not in ("ns", "telea"):
        raise HTTPException(400, "method doit être 'ns' ou 'telea'")

    job_id = str(uuid.uuid4())
    input_path = str(STORAGE_DIR / f"{job_id}_input.mp4")

    with open(input_path, "wb") as f:
        shutil.copyfileobj(video.file, f)

    jobs[job_id] = {"status": "queued"}

    background_tasks.add_task(
        process_video, job_id, input_path, x, y, w, h, method, radius
    )

    return {"job_id": job_id, "status": "queued"}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Vérifie l'état d'avancement d'un job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job introuvable")
    return {"job_id": job_id, "status": job["status"], "error": job.get("error")}


@app.get("/download/{job_id}")
async def download_result(job_id: str):
    """Télécharge la vidéo traitée une fois le job terminé."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job introuvable")
    if job["status"] != "done":
        raise HTTPException(400, f"Job pas encore prêt (statut actuel : {job['status']})")

    output_path = job["output_path"]
    if not os.path.exists(output_path):
        raise HTTPException(404, "Fichier de sortie introuvable")

    return FileResponse(output_path, media_type="video/mp4", filename="result.mp4")


@app.get("/health")
async def health():
    return {"status": "ok"}
