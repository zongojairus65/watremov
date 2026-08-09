"use client";

import { useState, useRef } from "react";

// Remplace par l'URL de ton backend Render déployé
const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://ton-backend.onrender.com";

export default function WatermarkRemover() {
  const [videoFile, setVideoFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [box, setBox] = useState(null); // {x, y, w, h}
  const [drawing, setDrawing] = useState(false);
  const [startPoint, setStartPoint] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | uploading | processing | done | error
  const [resultUrl, setResultUrl] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);

  function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    setVideoFile(file);
    setPreviewUrl(URL.createObjectURL(file));
    setBox(null);
    setStatus("idle");
    setResultUrl(null);
  }

  // Dessine le rectangle du watermark directement sur la vidéo en pause
  // Supporte à la fois souris (desktop) et tactile (mobile)
  function getRelativeCoords(e) {
    const rect = videoRef.current.getBoundingClientRect();
    const scaleX = videoRef.current.videoWidth / rect.width;
    const scaleY = videoRef.current.videoHeight / rect.height;
    // e.touches existe pour les événements tactiles, sinon on utilise l'événement souris directement
    const point = e.touches && e.touches.length > 0 ? e.touches[0] : e;
    return {
      x: Math.round((point.clientX - rect.left) * scaleX),
      y: Math.round((point.clientY - rect.top) * scaleY),
    };
  }

  function handleDrawStart(e) {
    e.preventDefault(); // empêche le scroll de la page pendant le dessin tactile
    setDrawing(true);
    setStartPoint(getRelativeCoords(e));
  }

  function handleDrawMove(e) {
    if (!drawing || !startPoint) return;
    e.preventDefault();
    const current = getRelativeCoords(e);
    setBox({
      x: Math.min(startPoint.x, current.x),
      y: Math.min(startPoint.y, current.y),
      w: Math.abs(current.x - startPoint.x),
      h: Math.abs(current.y - startPoint.y),
    });
  }

  function handleDrawEnd() {
    setDrawing(false);
  }

  async function handleSubmit() {
    if (!videoFile || !box) {
      setErrorMsg("Sélectionne une vidéo et dessine la zone du watermark");
      return;
    }

    setStatus("uploading");
    setErrorMsg(null);

    const formData = new FormData();
    formData.append("video", videoFile);
    formData.append("x", box.x);
    formData.append("y", box.y);
    formData.append("w", box.w);
    formData.append("h", box.h);
    formData.append("method", "ns");
    formData.append("radius", 4);

    try {
      const res = await fetch(`${API_URL}/remove-watermark`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Échec de l'envoi");
      const data = await res.json();

      setStatus("processing");
      pollStatus(data.job_id);
    } catch (err) {
      setStatus("error");
      setErrorMsg(err.message);
    }
  }

  async function pollStatus(jobId) {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/status/${jobId}`);
        const data = await res.json();

        if (data.status === "done") {
          clearInterval(interval);
          setResultUrl(`${API_URL}/download/${jobId}`);
          setStatus("done");
        } else if (data.status === "failed") {
          clearInterval(interval);
          setStatus("error");
          setErrorMsg(data.error || "Le traitement a échoué");
        }
        // sinon on continue à poller (queued / processing)
      } catch (err) {
        clearInterval(interval);
        setStatus("error");
        setErrorMsg(err.message);
      }
    }, 2000);
  }

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Watermark Remover</h1>

      <input
        type="file"
        accept="video/*"
        onChange={handleFileChange}
        className="block w-full text-sm"
      />

      {previewUrl && (
        <div className="space-y-2">
          <p className="text-sm text-gray-600">
            Mets la vidéo en pause sur une frame avec le watermark visible,
            puis dessine un rectangle dessus.
          </p>
          <div className="relative">
            <video
              ref={videoRef}
              src={previewUrl}
              controls
              className="w-full border rounded cursor-crosshair touch-none"
              onMouseDown={handleDrawStart}
              onMouseMove={handleDrawMove}
              onMouseUp={handleDrawEnd}
              onTouchStart={handleDrawStart}
              onTouchMove={handleDrawMove}
              onTouchEnd={handleDrawEnd}
            />
            {box && videoRef.current && (
              <div
                className="absolute border-2 border-red-500 bg-red-500/20 pointer-events-none"
                style={{
                  left: `${(box.x / videoRef.current.videoWidth) * 100}%`,
                  top: `${(box.y / videoRef.current.videoHeight) * 100}%`,
                  width: `${(box.w / videoRef.current.videoWidth) * 100}%`,
                  height: `${(box.h / videoRef.current.videoHeight) * 100}%`,
                }}
              />
            )}
          </div>
          {box && (
            <p className="text-sm text-gray-500">
              Zone sélectionnée : x={box.x}, y={box.y}, w={box.w}, h={box.h}
            </p>
          )}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={!videoFile || !box || status === "uploading" || status === "processing"}
        className="px-4 py-2 bg-black text-white rounded disabled:opacity-40"
      >
        {status === "uploading" && "Envoi..."}
        {status === "processing" && "Traitement en cours..."}
        {(status === "idle" || status === "done" || status === "error") && "Supprimer le watermark"}
      </button>

      {errorMsg && <p className="text-red-600 text-sm">{errorMsg}</p>}

      {resultUrl && (
        <div className="space-y-2">
          <p className="text-green-700 text-sm">Traitement terminé !</p>
          <a
            href={resultUrl}
            download
            className="inline-block px-4 py-2 border rounded"
          >
            Télécharger le résultat
          </a>
        </div>
      )}
    </div>
  );
}
