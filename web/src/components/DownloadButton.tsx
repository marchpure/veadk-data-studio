import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";
import { useDownload } from "@/hooks/useDownload";
import { trackDownloadClick } from "@/lib/analytics";

interface DownloadButtonProps {
  size?: "default" | "lg";
}

const DownloadButton = ({ size = "default" }: DownloadButtonProps) => {
  const { isMac, architecture, appleUrl, intelUrl } = useDownload();

  const isLarge = size === "lg";
  const buttonClass = isLarge ? "gap-2 text-lg px-8 py-6" : "gap-2";
  const iconClass = isLarge ? "h-5 w-5" : "h-4 w-4";

  const fireDownload = (arch: "apple-silicon" | "intel" | "unknown", url: string) =>
    trackDownloadClick({ location: "download_button", arch, url, is_mac: isMac });

  if (isMac && architecture !== "unknown") {
    const isAppleSilicon = architecture === "apple-silicon";
    const url = isAppleSilicon ? appleUrl : intelUrl;
    const label = isAppleSilicon ? "Download for Mac (Apple Silicon)" : "Download for Mac (Intel)";

    return (
      <Button size={size} className={buttonClass} asChild>
        <a href={url} onClick={() => fireDownload(architecture, url)}>
          <Download className={iconClass} />
          {label}
        </a>
      </Button>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <Button size={size} className={buttonClass} asChild>
          <a href={appleUrl} onClick={() => fireDownload("apple-silicon", appleUrl)}>
            <Download className={iconClass} />
            Download for Mac (Apple Silicon)
          </a>
        </Button>
        <Button size={size} variant="outline" className={buttonClass} asChild>
          <a href={intelUrl} onClick={() => fireDownload("intel", intelUrl)}>
            <Download className={iconClass} />
            Download for Mac (Intel)
          </a>
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        {isMac ? "Select your Mac type" : "Currently available for macOS only"}
      </p>
    </div>
  );
};

export default DownloadButton;
