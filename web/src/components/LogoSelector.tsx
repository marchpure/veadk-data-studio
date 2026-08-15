import { useState } from "react";
import logoPurple from "@/assets/byaan-logo-purple.png";
import logoOrange from "@/assets/byaan-logo-orange.png";
import logoBlue from "@/assets/byaan-logo-blue.png";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const logos = [
  { id: "purple", src: logoPurple, name: "Purple Gradient", colors: "Purple & Cyan" },
  { id: "orange", src: logoOrange, name: "Orange Gradient", colors: "Orange & Pink" },
  { id: "blue", src: logoBlue, name: "Blue Gradient", colors: "Blue & Cyan" },
];

export const LogoSelector = () => {
  const [selectedLogo, setSelectedLogo] = useState("purple");

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <Card className="p-4 bg-card/95 backdrop-blur-sm border-border shadow-xl">
        <p className="text-sm font-mono mb-3 text-muted-foreground">Logo Options:</p>
        <div className="flex gap-3">
          {logos.map((logo) => (
            <button
              key={logo.id}
              onClick={() => setSelectedLogo(logo.id)}
              className={`relative group p-2 rounded-lg transition-all ${
                selectedLogo === logo.id
                  ? "bg-primary/20 ring-2 ring-primary"
                  : "bg-secondary hover:bg-secondary/80"
              }`}
              title={logo.colors}
            >
              <img src={logo.src} alt={logo.name} className="h-12 w-12" />
              <div className="absolute -top-2 -right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="bg-background/90 backdrop-blur text-xs px-2 py-1 rounded border border-border whitespace-nowrap">
                  {logo.colors}
                </div>
              </div>
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-3 text-center">
          Click to preview different styles
        </p>
      </Card>
    </div>
  );
};

export const useSelectedLogo = () => {
  return logoPurple; // Default for now
};
