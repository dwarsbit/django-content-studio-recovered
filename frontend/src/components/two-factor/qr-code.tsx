import { useMemo } from "react";
import { encode } from "uqr";

/**
 * A QR code drawn as SVG from text (an otpauth:// link). Always dark on
 * white, whatever the theme: phone cameras read that best.
 */
export function QrCode({
  value,
  size = 168,
  label,
}: {
  value: string;
  size?: number;
  label: string;
}) {
  const path = useMemo(() => {
    const { data } = encode(value, { ecc: "M", border: 0 });
    let d = "";

    data.forEach((row, y) =>
      row.forEach((dark, x) => {
        if (dark) d += `M${x} ${y}h1v1h-1z`;
      }),
    );

    return { d, count: data.length };
  }, [value]);

  return (
    <div className="inline-flex rounded-lg border bg-white p-3">
      <svg
        role="img"
        aria-label={label}
        width={size}
        height={size}
        viewBox={`0 0 ${path.count} ${path.count}`}
        shapeRendering="crispEdges"
      >
        <path d={path.d} fill="#09090b" />
      </svg>
    </div>
  );
}
