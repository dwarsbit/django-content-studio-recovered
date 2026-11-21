import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PiArrowSquareOutBold,
  PiCaretDownBold,
  PiCheckBold,
  PiCopyBold,
  PiEyeBold,
  PiFloppyDiskBold,
  PiLinkBold,
  PiShareNetworkBold,
} from "react-icons/pi";
import { toast } from "sonner";

import { formatShortTime } from "@/components/publishing/publishing";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { DateTimeWidget } from "@/components/widgets/date-time-widget";
import { useHttp } from "@/hooks/use-http";
import { useContentLanguage } from "@/lib/content-language";
import { isSafeHref } from "@/lib/html";
import { getErrorMessage } from "@/lib/utils";
import {
  FieldType,
  type ModelField,
  type Resource,
  type SharedLink,
} from "@/types";

const DATE_FIELD: ModelField = {
  type: FieldType.DateTimeField,
  required: true,
};

function absolute(url: string) {
  return new URL(url, window.location.origin).toString();
}

async function writeClipboard(text: string) {
  await navigator.clipboard.writeText(text);
}

/**
 * The edit header's page button, in View on site's place: the main part
 * opens the object's page in a new tab (View on site when it is live,
 * Preview while it is not, with a preview token); its menu copies the
 * link and, for content that is not live, shares a draft link.
 */
export function PreviewButton({
  resource,
  resourcePath,
  viewOnSiteUrl,
  isDirty,
  onSave,
}: {
  resource: Resource;
  resourcePath: string;
  viewOnSiteUrl: string;
  isDirty: boolean;
  // Saves the form; resolves whether it saved.
  onSave(): Promise<boolean>;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const { language, config } = useContentLanguage();
  const [sharing, setSharing] = useState(false);
  const preview = resource.__preview__;
  const live = !preview || preview.live;
  // The page in the content language shown, when it is not the default.
  const contentLanguage =
    config && language && language !== config.default ? language : null;

  // The link to open or copy: the server adds a preview token for
  // content that is not live, and gives the page per language.
  async function pageUrl() {
    if (live && !contentLanguage) {
      return absolute(viewOnSiteUrl);
    }

    const { data } = await http.post<{ url: string }>(
      `${resourcePath}/${resource.id}/preview`,
      { language: contentLanguage },
    );

    if (!isSafeHref(data.url)) {
      throw new Error("Unsafe URL");
    }

    return absolute(data.url);
  }

  async function open() {
    if (live && !contentLanguage) {
      window.open(absolute(viewOnSiteUrl), "_blank", "noopener,noreferrer");
      return;
    }

    // Opened before the request, so the browser does not block it.
    const tab = window.open("", "_blank");

    try {
      const url = await pageUrl();

      if (tab) {
        tab.opener = null;
        tab.location.href = url;
      }
    } catch (error) {
      tab?.close();
      toast.error(getErrorMessage(error) as string);
    }
  }

  async function copy() {
    try {
      await writeClipboard(await pageUrl());
      toast.success(t(live ? "preview.link_copied" : "preview.preview_copied"));
    } catch (error) {
      toast.error(getErrorMessage(error) as string);
    }
  }

  const label = t(live ? "editor.view_on_site" : "preview.preview_draft");
  const tooltip = isDirty
    ? t("preview.tooltip_saved_version", { label })
    : live
      ? label
      : t("preview.tooltip_draft");

  return (
    <>
      <div className="flex items-center" data-testid="preview-button">
        <Tooltip>
          <TooltipTrigger asChild>
            {live && !contentLanguage ? (
              // A plain link: middle-click and "Open in new tab" work.
              <Button
                asChild
                size="icon"
                variant="ghost"
                className="rounded-r-none"
              >
                <a
                  href={viewOnSiteUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={label}
                >
                  <PiArrowSquareOutBold />
                </a>
              </Button>
            ) : (
              <Button
                size="icon"
                variant="ghost"
                aria-label={label}
                className="rounded-r-none"
                onClick={open}
              >
                {live ? <PiArrowSquareOutBold /> : <PiEyeBold />}
              </Button>
            )}
          </TooltipTrigger>
          <TooltipContent>{tooltip}</TooltipContent>
        </Tooltip>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              aria-label={t("preview.menu")}
              className="h-8 w-4 rounded-l-none px-0 text-muted-foreground"
            >
              <PiCaretDownBold className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-56">
            <DropdownMenuItem className="justify-start" onSelect={open}>
              {live ? <PiArrowSquareOutBold /> : <PiEyeBold />}
              {label}
            </DropdownMenuItem>
            {!live && isDirty && (
              <DropdownMenuItem
                className="justify-start"
                onSelect={async () => {
                  if (await onSave()) {
                    await open();
                  }
                }}
              >
                <PiFloppyDiskBold />
                {t("preview.save_and_preview")}
              </DropdownMenuItem>
            )}
            <DropdownMenuItem className="justify-start" onSelect={copy}>
              <PiLinkBold />
              {live ? (
                t("preview.copy_link")
              ) : (
                <span className="flex flex-col">
                  <span>{t("preview.copy_preview_link")}</span>
                  <span className="text-xs text-muted-foreground">
                    {t("preview.copy_preview_link_hint")}
                  </span>
                </span>
              )}
            </DropdownMenuItem>
            {!live && preview?.can_share && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="justify-start"
                  onSelect={() => setSharing(true)}
                >
                  <PiShareNetworkBold />
                  {t("preview.share")}
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {preview?.can_share && (
        <ShareDialog
          open={sharing}
          onOpenChange={setSharing}
          resource={resource}
          resourcePath={resourcePath}
        />
      )}
    </>
  );
}

const EXPIRY = ["1", "7", "30", "date", "none"] as const;
type Expiry = (typeof EXPIRY)[number];

function expiresAt(expiry: Expiry, date: string | null): string | null {
  if (expiry === "none") {
    return null;
  }

  if (expiry === "date") {
    return date;
  }

  return dayjs().add(Number(expiry), "day").format();
}

/**
 * Share draft link: a link anyone can open to see the draft on the
 * site, until it expires or is revoked, and the object's active links.
 */
export function ShareDialog({
  open,
  onOpenChange,
  resource,
  resourcePath,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  resource: Resource;
  resourcePath: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="grid-cols-[minmax(0,1fr)] sm:max-w-lg">
        {/* Mounted per opening, so it starts fresh. */}
        {open && (
          <ShareForm
            resource={resource}
            resourcePath={resourcePath}
            onClose={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ShareForm({
  resource,
  resourcePath,
  onClose,
}: {
  resource: Resource;
  resourcePath: string;
  onClose(): void;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const queryClient = useQueryClient();
  const { language, config } = useContentLanguage();
  const [expiry, setExpiry] = useState<Expiry>("7");
  const [date, setDate] = useState<string | null>(
    dayjs().add(14, "day").hour(18).minute(0).second(0).format(),
  );
  const [note, setNote] = useState("");
  const [shareLanguage, setShareLanguage] = useState(language);
  const [created, setCreated] = useState<SharedLink | null>(null);
  const [copied, setCopied] = useState(false);
  const path = `${resourcePath}/${resource.id}/preview-links`;
  const queryKey = ["preview-links", path];

  const { data: links = [] } = useQuery({
    queryKey,
    async queryFn() {
      const { data } = await http.get<{ links: SharedLink[] }>(path);
      return data.links;
    },
  });

  const { mutate: create, isPending } = useMutation({
    async mutationFn() {
      const { data } = await http.post<{
        created: SharedLink;
        links: SharedLink[];
      }>(path, {
        expires_at: expiresAt(expiry, date),
        note,
        language: config ? shareLanguage : null,
      });
      return data;
    },
    onSuccess(data) {
      queryClient.setQueryData(queryKey, data.links);
      setCreated(data.created);
    },
    onError(error) {
      const data = (error as { response?: { data?: unknown } })?.response
        ?.data as Record<string, string[]> | undefined;
      toast.error(data?.expires_at?.[0] ?? (getErrorMessage(error) as string));
    },
  });

  const { mutate: revoke } = useMutation({
    async mutationFn(id: number) {
      await http.delete(`${path}/${id}`);
    },
    async onSuccess() {
      await queryClient.invalidateQueries({ queryKey });
      toast.success(t("preview.revoked"));
    },
  });

  const createdUrl =
    created?.url && isSafeHref(created.url) ? absolute(created.url) : null;
  const others = links.filter((link) => link.id !== created?.id);
  const languageName = (code: string | null) =>
    config?.languages.find((option) => option.code === code)?.code ?? code;

  function describe(link: SharedLink) {
    return [
      link.created_by && t("preview.by", { name: link.created_by }),
      link.expires_at
        ? t("preview.expires_short", {
            date: formatShortTime(link.expires_at),
          })
        : t("preview.no_expiry"),
      link.opens
        ? t("preview.opened", { count: link.opens })
        : t("preview.not_opened"),
    ]
      .filter(Boolean)
      .join(" · ");
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("preview.share_title")}</DialogTitle>
        <DialogDescription>
          {t("preview.share_description", { name: resource.__str__ })}
        </DialogDescription>
      </DialogHeader>
      {createdUrl ? (
        <div className="space-y-2">
          <Label htmlFor="share-url">{t("preview.new_link")}</Label>
          <div className="flex gap-2">
            <Input
              id="share-url"
              readOnly
              value={createdUrl}
              className="font-mono text-xs"
              onFocus={(event) => event.currentTarget.select()}
            />
            <Button
              variant="outline"
              onClick={async () => {
                try {
                  await writeClipboard(createdUrl);
                  setCopied(true);
                  toast.success(t("preview.link_copied"));
                } catch (error) {
                  toast.error(getErrorMessage(error) as string);
                }
              }}
            >
              {copied ? <PiCheckBold /> : <PiCopyBold />}
              {t(copied ? "preview.copied" : "preview.copy")}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {created?.expires_at
              ? t("preview.expires_on", {
                  date: formatShortTime(created.expires_at),
                })
              : t("preview.never_expires")}
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="share-expiry">{t("preview.expires")}</Label>
            <Select
              value={expiry}
              onValueChange={(value) => setExpiry(value as Expiry)}
            >
              <SelectTrigger id="share-expiry" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXPIRY.map((option) => (
                  <SelectItem key={option} value={option}>
                    {t(`preview.expiry_${option}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {config && (
            <div className="space-y-2">
              <Label htmlFor="share-language">{t("preview.language")}</Label>
              <Select value={shareLanguage} onValueChange={setShareLanguage}>
                <SelectTrigger id="share-language" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {config.languages.map((option) => (
                    <SelectItem key={option.code} value={option.code}>
                      {option.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {expiry === "date" && (
            <div className="space-y-2 sm:col-span-2">
              <Label>{t("preview.expires_at")}</Label>
              <DateTimeWidget
                field={DATE_FIELD}
                value={date}
                options={{ min_date: dayjs().format("YYYY-MM-DD") }}
                onChange={setDate}
              />
            </div>
          )}
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="share-note">
              {t("preview.note")}{" "}
              <span className="font-normal text-muted-foreground">
                {t("preview.note_hint")}
              </span>
            </Label>
            <Input
              id="share-note"
              value={note}
              maxLength={200}
              placeholder={t("preview.note_placeholder")}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
        </div>
      )}
      {others.length > 0 && (
        <div className="space-y-2">
          <Label>{t("preview.active_links")}</Label>
          <ul className="divide-y rounded-lg border">
            {others.map((link) => (
              <li
                key={link.id}
                className="flex items-center gap-3 px-3 py-2 text-sm"
              >
                <PiLinkBold className="size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">
                    {link.note || t("preview.untitled")}
                    {config && link.language && (
                      <span className="ml-1.5 text-xs font-normal text-muted-foreground uppercase">
                        {languageName(link.language)}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {describe(link)}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={() => revoke(link.id)}
                >
                  {t("preview.revoke")}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <DialogFooter>
        {createdUrl ? (
          <Button onClick={onClose}>{t("common.done")}</Button>
        ) : (
          <>
            <Button variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button
              disabled={isPending || (expiry === "date" && !date)}
              onClick={() => create()}
            >
              {t("preview.create")}
            </Button>
          </>
        )}
      </DialogFooter>
    </>
  );
}
