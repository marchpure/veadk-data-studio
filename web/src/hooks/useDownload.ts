import { useState, useEffect } from "react";

const DOWNLOAD_API_URL =
  "https://downloads.byaan.ai/stable/download.json";

const FALLBACK_APPLE_URL =
  "https://downloads.byaan.ai/stable/arm64/Byaan.dmg";
const FALLBACK_INTEL_URL =
  "https://downloads.byaan.ai/stable/x64/Byaan.dmg";

interface DownloadData {
  version: string;
  platforms: {
    "darwin-x86_64": { url: string };
    "darwin-aarch64": { url: string };
  };
}

type Architecture = "apple-silicon" | "intel" | "unknown";

// Simple Mac detection
function isMacDevice(): boolean {
  if (typeof navigator === "undefined") return false;
  return navigator.platform?.includes("Mac") || navigator.userAgent?.includes("Macintosh");
}

// Detect architecture using Client Hints API
async function detectArchitecture(): Promise<Architecture> {
  if (!isMacDevice()) return "unknown";

  try {
    if (navigator.userAgentData?.getHighEntropyValues) {
      const { architecture } = await navigator.userAgentData.getHighEntropyValues(["architecture"]);
      if (architecture === "arm") return "apple-silicon";
      if (architecture === "x86") return "intel";
    }
  } catch {
    // Safari/Firefox don't support this API
  }

  return "unknown";
}

// Cache to avoid refetching
const cache: { data: DownloadData | null; architecture: Architecture | null } = {
  data: null,
  architecture: null,
};

export function useDownload() {
  const [data, setData] = useState<DownloadData | null>(cache.data);
  const [architecture, setArchitecture] = useState<Architecture>(cache.architecture ?? "unknown");
  const [isLoading, setIsLoading] = useState(!cache.data);

  const isMac = isMacDevice();

  useEffect(() => {
    async function init() {
      // Detect architecture once
      if (!cache.architecture) {
        cache.architecture = await detectArchitecture();
        setArchitecture(cache.architecture);
      }

      // Fetch download URLs once
      if (!cache.data) {
        try {
          const res = await fetch(DOWNLOAD_API_URL);
          if (res.ok) {
            cache.data = await res.json();
            setData(cache.data);
          }
        } catch {
          // Silently fail - buttons will be disabled
        }
      }

      setIsLoading(false);
    }

    init();
  }, []);

  return {
    isMac,
    architecture,
    appleUrl: data?.platforms["darwin-aarch64"]?.url ?? FALLBACK_APPLE_URL,
    intelUrl: data?.platforms["darwin-x86_64"]?.url ?? FALLBACK_INTEL_URL,
    isLoading,
  };
}
