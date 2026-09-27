import { createRoot } from "react-dom/client";
import { CommunityDemoContent } from "../portal/app/dashboard/community/page";

const root = document.getElementById("root");
if (!root) throw new Error("Community preview root is missing");

createRoot(root).render(
  <main className="min-h-screen bg-[#0d0d0d] text-[#FFF7ED]">
    <header className="border-b border-white/10">
      <div className="mx-auto flex max-w-7xl items-center px-5 py-4">
        <span className="font-mono text-sm font-bold tracking-wide text-[#ff9b63]">PYTORCH PH</span>
      </div>
    </header>
    <div className="mx-auto max-w-7xl px-5 py-8 lg:py-10"><CommunityDemoContent /></div>
  </main>,
);
