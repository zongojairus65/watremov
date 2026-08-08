"""
Watermark Remover - OpenCV inpainting pour vidéo
Fonctionne pour watermark fixe (logo statique) et watermark qui bouge (via masques par frame).

Usage basique (watermark fixe) :
    python watermark_remover.py input.mp4 output.mp4 --x 10 --y 10 --w 150 --h 60

Usage avancé (masque personnalisé par frame) :
    Voir la fonction remove_watermark_dynamic() plus bas.

Notes issues des tests :
- Méthode "ns" (Navier-Stokes) donne un meilleur rendu que "telea" sur les fonds
  en dégradé ou les bordures de letterboxing (bandes noires).
- Ajuster x/y/w/h au plus près du texte réel améliore nettement le résultat :
  extraire une frame (ffmpeg -i video.mp4 -vframes 1 frame.png), zoomer dessus
  pour repérer les coordonnées exactes avant de lancer le traitement complet.
- Limite connue : sur fond avec dégradé fin ou transition complexe, une légère
  trace peut rester visible (watermark illisible mais zone perceptible).
  Pour un résultat totalement invisible dans ces cas, il faudrait un modèle
  de deep learning (ProPainter et similaires), non couvert par ce script.
"""

import cv2
import numpy as np
import subprocess
import argparse
import os
import tempfile


def build_mask(frame_shape, x, y, w, h, feather=5):
    """
    Crée un masque binaire pour la zone du watermark.
    feather : agrandit légèrement la zone pour mieux capturer les bords semi-transparents.
    """
    mask = np.zeros(frame_shape[:2], dtype=np.uint8)
    x1, y1 = max(0, x - feather), max(0, y - feather)
    x2, y2 = min(frame_shape[1], x + w + feather), min(frame_shape[0], y + h + feather)
    mask[y1:y2, x1:x2] = 255
    return mask


def remove_watermark_fixed(input_path, output_path, x, y, w, h,
                            inpaint_radius=3, method="telea"):
    """
    Supprime un watermark à position et taille fixes sur toute la vidéo.
    method : "telea" (rapide, bon pour zones petites) ou "ns" (Navier-Stokes, plus lisse)
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir la vidéo : {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    inpaint_flag = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS

    # Fichier temporaire sans audio, on réinjecte l'audio après avec ffmpeg
    tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(tmp_video, fourcc, fps, (width, height))

    mask = build_mask((height, width), x, y, w, h)

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        result = cv2.inpaint(frame, mask, inpaint_radius, inpaint_flag)
        writer.write(result)

        frame_idx += 1
        if frame_idx % 30 == 0:
            print(f"Traité {frame_idx}/{total_frames} frames")

    cap.release()
    writer.release()

    # Réinjection de l'audio original via ffmpeg
    _mux_audio(input_path, tmp_video, output_path)
    os.remove(tmp_video)

    print(f"Terminé : {output_path}")


def remove_watermark_dynamic(input_path, output_path, masks_per_frame,
                              inpaint_radius=3, method="telea"):
    """
    Supprime un watermark dont la position/taille varie.
    masks_per_frame : liste de masques numpy (un par frame, même ordre que la vidéo),
                       ou fonction callback(frame_idx, frame_shape) -> mask
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir la vidéo : {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    inpaint_flag = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS

    tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(tmp_video, fourcc, fps, (width, height))

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if callable(masks_per_frame):
            mask = masks_per_frame(frame_idx, frame.shape)
        else:
            mask = masks_per_frame[frame_idx]

        result = cv2.inpaint(frame, mask, inpaint_radius, inpaint_flag)
        writer.write(result)
        frame_idx += 1

    cap.release()
    writer.release()

    _mux_audio(input_path, tmp_video, output_path)
    os.remove(tmp_video)

    print(f"Terminé : {output_path}")


def _mux_audio(original_path, video_no_audio_path, output_path):
    """Réinjecte l'audio de la vidéo originale dans la vidéo traitée via ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_no_audio_path,
        "-i", original_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0?",  # ? = optionnel si pas d'audio dans l'original
        "-shortest",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Avertissement ffmpeg (audio possiblement absent) :", result.stderr[-300:])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Supprime un watermark fixe d'une vidéo")
    parser.add_argument("input", help="Chemin de la vidéo d'entrée")
    parser.add_argument("output", help="Chemin de la vidéo de sortie")
    parser.add_argument("--x", type=int, required=True, help="Position X du watermark")
    parser.add_argument("--y", type=int, required=True, help="Position Y du watermark")
    parser.add_argument("--w", type=int, required=True, help="Largeur du watermark")
    parser.add_argument("--h", type=int, required=True, help="Hauteur du watermark")
    parser.add_argument("--method", choices=["telea", "ns"], default="ns")
    parser.add_argument("--radius", type=int, default=4)

    args = parser.parse_args()
    remove_watermark_fixed(
        args.input, args.output,
        args.x, args.y, args.w, args.h,
        inpaint_radius=args.radius,
        method=args.method
    )
