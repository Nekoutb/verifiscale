'use client';

import { useEffect } from 'react';

/**
 * Global error boundary — replaces Next's white "Application error" page.
 *
 * Main real-world cause here: a tab left open across a deploy holds stale
 * content-hashed chunk references; the next navigation throws ChunkLoadError.
 * In that case reload ONCE automatically (sessionStorage flag prevents a
 * loop); otherwise show a proper French error screen with a reload button.
 */
export default function GlobalError({
  error, reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    const isStaleBundle = /ChunkLoadError|Loading chunk|dynamically imported module|import\(\) failed/i
      .test(`${error?.name ?? ''} ${error?.message ?? ''}`);
    const key = 'fa_chunk_reload';
    if (isStaleBundle && !window.sessionStorage.getItem(key)) {
      window.sessionStorage.setItem(key, '1');
      window.location.reload();
    } else {
      window.sessionStorage.removeItem(key);
    }
  }, [error]);

  return (
    <html lang="fr">
      <body style={{
        fontFamily: 'system-ui, -apple-system, sans-serif', margin: 0,
        display: 'flex', minHeight: '100vh', alignItems: 'center',
        justifyContent: 'center', background: '#fafafa', color: '#111',
      }}>
        <div style={{ textAlign: 'center', maxWidth: 440, padding: 24 }}>
          <div style={{ fontSize: 34, marginBottom: 8 }}>⚠️</div>
          <h1 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>
            Une erreur est survenue
          </h1>
          <p style={{ fontSize: 13, color: '#555', marginTop: 10, lineHeight: 1.5 }}>
            L&apos;application a probablement été mise à jour pendant que cette
            page était ouverte. Rechargez pour obtenir la dernière version —
            votre session et vos données ne sont pas affectées.
          </p>
          <div style={{ marginTop: 18, display: 'flex', gap: 8, justifyContent: 'center' }}>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: '9px 22px', background: '#000', color: '#fff',
                borderRadius: 8, fontSize: 13, fontWeight: 600,
                border: 'none', cursor: 'pointer',
              }}
            >
              Recharger l&apos;application
            </button>
            <button
              onClick={reset}
              style={{
                padding: '9px 22px', background: '#fff', color: '#000',
                borderRadius: 8, fontSize: 13, fontWeight: 500,
                border: '1px solid #d4d4d4', cursor: 'pointer',
              }}
            >
              Réessayer
            </button>
          </div>
          {error?.digest && (
            <p style={{ fontSize: 10, color: '#999', marginTop: 14, fontFamily: 'monospace' }}>
              ref: {error.digest}
            </p>
          )}
        </div>
      </body>
    </html>
  );
}
