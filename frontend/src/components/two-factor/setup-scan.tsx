import { useTranslation } from "react-i18next";

import { QrCode } from "./qr-code";
import { SecretKey } from "./secret-key";

/** The QR code with the key beside it, for apps that cannot scan. */
export function SetupScan({
  data,
  size = 120,
}: {
  data: { secret: string; uri: string } | null | undefined;
  size?: number;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-4">
      <div className="shrink-0">
        {data ? (
          <QrCode
            value={data.uri}
            size={size}
            label={t("two_factor.qr_label")}
          />
        ) : (
          <div
            className="rounded-lg border bg-muted"
            style={{ width: size + 26, height: size + 26 }}
          />
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-2 text-sm">
        <p className="text-muted-foreground">{t("two_factor.scan")}</p>
        <p className="text-xs text-muted-foreground">
          {t("two_factor.cannot_scan")}
        </p>
        {data && <SecretKey secret={data.secret} />}
      </div>
    </div>
  );
}
