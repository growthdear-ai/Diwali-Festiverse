import { ArrowUp, Check, ShieldCheck } from "lucide-react";
import { NazarAvatar } from "@/components/common";
import { Tilt3D } from "@/components/ui/tilt";

/** Product illustration in a gentle 3D perspective. Labeled "Example"; not live data. */
export function HeroScene() {
  return (
    <div className="relative mx-auto w-full max-w-[880px]">
      <div className="absolute inset-x-16 -bottom-6 h-24 rounded-[50%] bg-black/10 blur-3xl" aria-hidden />
      <Tilt3D max={4} glare={false}>
        <div className="preserve-3d [transform:rotateX(14deg)] [transform-origin:50%_100%]">
          <div className="overflow-hidden rounded-[20px] border border-border bg-surface shadow-[var(--shadow-lg)]">
            {/* window header */}
            <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
              <div>
                <p className="text-[14px] font-semibold">Sharma Family</p>
                <p className="text-[12px] text-muted-foreground">5 members · 3 online</p>
              </div>
              <span className="text-[11px] text-subtle">Example</span>
            </div>

            <div className="grid gap-0 md:grid-cols-[1fr_260px]">
              {/* conversation */}
              <div className="space-y-4 p-5 text-left">
                <div className="flex justify-end">
                  <p className="max-w-[80%] rounded-[18px] rounded-br-[6px] bg-primary px-3.5 py-2 text-[13.5px] leading-relaxed text-white">
                    @Nazar Bangalore se Patna 4 Dec ka flight 6000 se kam ho toh batao.
                  </p>
                </div>
                <div className="flex items-end gap-2">
                  <NazarAvatar className="size-6" />
                  <p className="max-w-[80%] rounded-[18px] rounded-bl-[6px] bg-muted px-3.5 py-2 text-[13.5px] leading-relaxed">Watch activated. I&apos;ll monitor Bangalore → Patna for 4 Dec. Target ₹6,000.</p>
                </div>
                <div className="ml-8 max-w-[380px] rounded-[16px] border border-border p-4">
                  <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
                    <span className="font-medium text-foreground">Nazar</span> · Flight · just now
                    <span className="ml-auto inline-flex items-center gap-1 text-primary">
                      <ShieldCheck className="size-3.5" /> Verified
                    </span>
                  </div>
                  <p className="mt-3 text-[15px] font-semibold">Flight price dropped</p>
                  <div className="mt-2 flex items-baseline gap-3">
                    <span className="text-[26px] font-semibold tracking-[-0.03em] tabular-nums">₹5,640</span>
                    <span className="text-[13px] text-muted-foreground">
                      <span className="line-through">₹6,800</span> · <span className="text-primary">↓ 17%</span>
                    </span>
                  </div>
                  <div className="mt-3 inline-flex rounded-full bg-muted p-1 text-[12.5px] font-medium">
                    <span className="inline-flex items-center gap-1 rounded-full bg-surface px-3 py-1 shadow-[0_1px_2px_rgb(24_24_27/0.08)]">
                      <Check className="size-3 text-primary" /> Yes 2
                    </span>
                    <span className="px-3 py-1 text-muted-foreground">No 0</span>
                    <span className="px-3 py-1 text-muted-foreground">Wait 1</span>
                  </div>
                  <p className="mt-2 text-[12px] text-muted-foreground">Mummy and Papa voted Yes</p>
                </div>
                <div className="flex items-center gap-2 rounded-full border border-border-strong py-1 pl-4 pr-1 text-[13px] text-subtle">
                  Message, or type @Nazar
                  <span className="ml-auto grid size-7 place-items-center rounded-full bg-primary text-white">
                    <ArrowUp className="size-3.5" />
                  </span>
                </div>
              </div>

              {/* side panel */}
              <div className="hidden space-y-1 border-l border-border p-3 text-left md:block">
                <p className="px-2 pb-1 text-[12px] font-medium text-subtle">Watches</p>
                {[
                  ["BLR → PAT", "₹5,640", "Below ₹6,000"],
                  ["TATAMOTORS", "₹688.05", "Moves more than 3%"],
                  ["SSC CGL", "1 notice", "ssc.gov.in"],
                ].map(([t, v, s]) => (
                  <div key={t} className="rounded-[10px] px-2 py-2">
                    <div className="flex justify-between text-[13px]">
                      <span className="font-medium">{t}</span>
                      <span className="tabular-nums">{v}</span>
                    </div>
                    <p className="text-[11.5px] text-muted-foreground">{s}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </Tilt3D>
    </div>
  );
}
