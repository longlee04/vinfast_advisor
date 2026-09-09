import type { ModelViewerElement } from "@google/model-viewer";
import type { HTMLAttributes, RefAttributes } from "react";

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "model-viewer": HTMLAttributes<ModelViewerElement> & RefAttributes<ModelViewerElement> & {
        alt: string;
        "auto-rotate"?: boolean;
        "camera-controls"?: boolean;
        "camera-orbit"?: string;
        "environment-image"?: string;
        "interaction-prompt"?: "auto" | "none";
        loading?: "auto" | "lazy" | "eager";
        poster?: string;
        "shadow-intensity"?: string;
        src: string;
        "touch-action"?: string;
      };
    }
  }
}
