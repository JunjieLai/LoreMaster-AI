import { useState, useEffect } from 'react';

const API_BASE = 'http://localhost:8000';
const thumbnailCache = new Map<string, string | null>();

// Convert Fandom URL to proxied URL
function getProxiedUrl(originalUrl: string): string {
  return `${API_BASE}/api/image-proxy?url=${encodeURIComponent(originalUrl)}`;
}

export function useThumbnail(title: string): { thumbnailUrl: string | null; isLoading: boolean } {
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(
    thumbnailCache.get(title) ?? null
  );
  const [isLoading, setIsLoading] = useState(!thumbnailCache.has(title));

  useEffect(() => {
    // Check cache first
    if (thumbnailCache.has(title)) {
      setThumbnailUrl(thumbnailCache.get(title) ?? null);
      setIsLoading(false);
      return;
    }

    const fetchThumbnail = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/api/thumbnail/${encodeURIComponent(title)}`
        );
        if (response.ok) {
          const data = await response.json();
          // Use proxied URL to avoid CORS/referrer issues
          const proxiedUrl = data.thumbnail_url ? getProxiedUrl(data.thumbnail_url) : null;
          thumbnailCache.set(title, proxiedUrl);
          setThumbnailUrl(proxiedUrl);
        } else {
          thumbnailCache.set(title, null);
          setThumbnailUrl(null);
        }
      } catch (error) {
        console.error(`Failed to fetch thumbnail for ${title}:`, error);
        thumbnailCache.set(title, null);
        setThumbnailUrl(null);
      } finally {
        setIsLoading(false);
      }
    };

    fetchThumbnail();
  }, [title]);

  return { thumbnailUrl, isLoading };
}

// Batch fetch for multiple titles (used for preloading)
export async function prefetchThumbnails(titles: string[]): Promise<void> {
  const uncached = titles.filter((t) => !thumbnailCache.has(t));
  if (uncached.length === 0) return;

  try {
    const response = await fetch(`${API_BASE}/api/thumbnails/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ titles: uncached }),
    });

    if (response.ok) {
      const data = await response.json();
      Object.entries(data.thumbnails).forEach(([title, url]) => {
        thumbnailCache.set(title, url as string | null);
      });
    }
  } catch (error) {
    console.error('Failed to prefetch thumbnails:', error);
  }
}
