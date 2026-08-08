import "./globals.css";

export const metadata = {
  title: "Watermark Remover",
  description: "Supprime un watermark fixe d'une vidéo",
};

export default function RootLayout({ children }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
