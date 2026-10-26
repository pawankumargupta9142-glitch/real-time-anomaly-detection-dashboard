import React from "react";

const YOUTUBE_VIDEO_ID = "?si=328cJX7dgQSDIjv4";

const YOUTUBE_LIVE_URL =
  `https://www.youtube.com/live/jBvzOfT8_44?si=328cJX7dgQSDIjv4`;

export default function YouTubeLive() {
  return (
    <div style={styles.card}>

      {/* Header */}
      <div style={styles.header}>
        <div>
          <h2 style={styles.title}>🔴 Live Video</h2>
          <p style={styles.subtitle}>
            Real-Time YouTube Live Stream
          </p>
        </div>

        <div style={styles.liveBadge}>
          <span style={styles.liveDot}></span>
          LIVE
        </div>
      </div>

      {/* YouTube Video */}
      <div style={styles.videoContainer}>
        <iframe
          src={YOUTUBE_LIVE_URL}
          title="Risk Radar YouTube Live Stream"
          style={styles.iframe}
          allow="autoplay; encrypted-media; picture-in-picture; web-share"
          allowFullScreen
        />
      </div>

      {/* Footer */}
      <div style={styles.footer}>
        <span>📡 Live Stream</span>
        <span>Risk Radar</span>
      </div>

    </div>
  );
}


/* =====================================================
   STYLES
===================================================== */

const styles = {
  card: {
    width: "100%",
    background: "#111827",
    border: "1px solid #26334d",
    borderRadius: "16px",
    padding: "18px",
    boxSizing: "border-box",
    marginBottom: "20px",
    boxShadow: "0 8px 30px rgba(0, 0, 0, 0.25)",
  },

  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: "15px",
  },

  title: {
    margin: 0,
    color: "#ffffff",
    fontSize: "21px",
    fontWeight: "700",
  },

  subtitle: {
    margin: "5px 0 0",
    color: "#94a3b8",
    fontSize: "13px",
  },

  liveBadge: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    background: "#7f1d1d",
    color: "#ffffff",
    padding: "7px 12px",
    borderRadius: "20px",
    fontSize: "12px",
    fontWeight: "700",
  },

  liveDot: {
    width: "8px",
    height: "8px",
    background: "#ef4444",
    borderRadius: "50%",
    display: "inline-block",
    boxShadow: "0 0 8px #ef4444",
  },

  videoContainer: {
    position: "relative",
    width: "100%",
    aspectRatio: "16 / 9",
    overflow: "hidden",
    borderRadius: "12px",
    background: "#000000",
  },

  iframe: {
    width: "100%",
    height: "100%",
    border: "none",
    display: "block",
  },

  footer: {
    display: "flex",
    justifyContent: "space-between",
    marginTop: "12px",
    color: "#64748b",
    fontSize: "12px",
  },
};
