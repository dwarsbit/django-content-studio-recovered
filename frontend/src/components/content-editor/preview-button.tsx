// MOCKUP SPIKE (previews): the View on site / Preview split button and
// the Share draft link dialog. Strings are English only; not for merge.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
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
import { useHttp } from "@/hooks/use-http";
import { useContentLanguage } from "@/lib/content-language";
import { cn } from "@/lib/utils";
import type { Resource } from "@/types";

interface SharedLink {
  id: string;
  url: string;
  note: string;
  language: string | null;
  created_by: string;
  created_at: string;
  expires_at: string | null;
  opens: number;
  last_opened_at: string | null;
}

async function copy(text: string, message: string) {
  try {
    await navigator.clipboard?.writeText(text);
  } catch {
    // Clipboard refused (no focus): the toast still shows in mockups.
  }
  toast.success(message);
}

function absolute(url: string) {
  return new URL(url, window.location.origin).toString();
}

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
  onSave(): Promise<void>;
}) {
  const http = useHttp();
  const { language, config } = useContentLanguage();
  const [sharing, setSharing] = useState(false);
  const state = resource.__publishing__?.state;
  const live = !state || state === "published";
  const contentLanguage = config ? language : null;

  async function staffUrl() {
    const { data } = await http.post<{ url: string }>(
      `${resourcePath}/${resource.id}/preview`,
      { language: contentLanguage },
    );
    return absolute(data.url);
  }

  async function openPreview() {
    if (live) {
      window.open(viewOnSiteUrl, "_blank", "noopener,noreferrer");
      return;
    }
    const tab = window.open("", "_blank");
    const url = await staffUrl();
    if (tab) {
      tab.opener = null;
      tab.location.href = url;
    }
  }

  const label = live ? "View on site" : "Preview draft";
  const tooltip = live
    ? isDirty
      ? "View on site · shows the last saved version"
      : "View on site"
    : isDirty
      ? "Preview draft · shows the last saved version"
      : "Preview draft · only people with a link can see it";

  return (
    <>
      <div
        className="flex items-center rounded-lg"
        data-testid="preview-split"
      >
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              aria-label={label}
              className="rounded-r-none"
              onClick={openPreview}
            >
              {live ? <PiArrowSquareOutBold /> : <PiEyeBold />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{tooltip}</TooltipContent>
        </Tooltip>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              aria-label="Preview and share"
              className="h-8 w-4 rounded-l-none px-0 text-muted-foreground"
            >
              <PiCaretDownBold className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            {live ? (
              <>
                <DropdownMenuItem className="justify-start" onSelect={openPreview}>
                  <PiArrowSquareOutBold />
                  View on site
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="justify-start"
                  onSelect={() =>
                    copy(absolute(viewOnSiteUrl), "Link copied")
                  }
                >
                  <PiLinkBold />
                  Copy link
                </DropdownMenuItem>
              </>
            ) : (
              <>
                <DropdownMenuItem className="justify-start" onSelect={openPreview}>
                  <PiEyeBold />
                  Preview draft
                </DropdownMenuItem>
                {isDirty && (
                  <DropdownMenuItem
                    className="justify-start"
                    onSelect={async () => {
                      await onSave();
                      await openPreview();
                    }}
                  >
                    <PiFloppyDiskBold />
                    Save and preview
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem
                  className="justify-start"
                  onSelect={async () =>
                    copy(
                      await staffUrl(),
                      "Preview link copied · works for you for 1 hour",
                    )
                  }
                >
                  <PiLinkBold />
                  <span className="flex flex-col">
                    <span>Copy preview link</span>
                    <span className="text-xs text-muted-foreground">
                      For you, for 1 hour
                    </span>
                  </span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="justify-start" onSelect={() => setSharing(true)}>
                  <PiShareNetworkBold />
                  Share draft link…
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <ShareDialog
        open={sharing}
        onOpenChange={setSharing}
        resource={resource}
        resourcePath={resourcePath}
      />
    </>
  );
}

const EXPIRY = [
  { value: "1", label: "1 day" },
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "date", label: "On a date…" },
  { value: "0", label: "No expiry" },
];

function describe(link: SharedLink) {
  const parts = [`By ${link.created_by}`];
  parts.push(
    link.expires_at
      ? `expires ${dayjs(link.expires_at).format("D MMM")}`
      : "no expiry",
  );
  parts.push(
    link.opens
      ? `opened ${link.opens} ${link.opens === 1 ? "time" : "times"}`
      : "not opened yet",
  );
  return parts.join(" · ");
}

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
  const http = useHttp();
  const queryClient = useQueryClient();
  const { language, config } = useContentLanguage();
  const [days, setDays] = useState("7");
  const [note, setNote] = useState("");
  const [lang, setLang] = useState<string>(language);
  const [created, setCreated] = useState<SharedLink | null>(null);
  const [copied, setCopied] = useState(false);
  const key = ["preview-links", resourcePath, resource.id];
  const { data: links = [] } = useQuery({
    queryKey: key,
    enabled: open,
    async queryFn() {
      const { data } = await http.get<SharedLink[]>(
        `${resourcePath}/${resource.id}/preview-links`,
      );
      return data;
    },
  });
  const { mutateAsync: create, isPending } = useMutation({
    async mutationFn() {
      const { data } = await http.post<SharedLink[]>(
        `${resourcePath}/${resource.id}/preview-links`,
        {
          days: days === "date" ? 14 : Number(days),
          note,
          language: config ? lang : null,
        },
      );
      return data;
    },
    onSuccess(data) {
      queryClient.setQueryData(key, data);
      setCreated(data[0]);
      setCopied(false);
    },
  });
  const { mutateAsync: revoke } = useMutation({
    async mutationFn(id: string) {
      await http.delete(`${resourcePath}/${resource.id}/preview-links/${id}`);
    },
    async onSuccess() {
      await queryClient.invalidateQueries({ queryKey: key });
      toast.success("Link revoked");
    },
  });
  const others = links.filter((link) => link.id !== created?.id);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) {
          setCreated(null);
          setNote("");
          setDays("7");
        }
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Share draft link</DialogTitle>
          <DialogDescription>
            Anyone with the link can see this draft of “{resource.__str__}”
            until the link expires or you revoke it. It shows the last saved
            version.
          </DialogDescription>
        </DialogHeader>
        {created ? (
          <div className="space-y-2">
            <Label>New link</Label>
            <div className="flex gap-2">
              <Input
                readOnly
                value={absolute(created.url)}
                className="font-mono text-xs"
                onFocus={(event) => event.currentTarget.select()}
              />
              <Button
                variant="outline"
                onClick={async () => {
                  await copy(absolute(created.url), "Link copied");
                  setCopied(true);
                }}
              >
                {copied ? <PiCheckBold /> : <PiCopyBold />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              {created.expires_at
                ? `Expires ${dayjs(created.expires_at).format("D MMMM YYYY, HH:mm")}.`
                : "Never expires. Revoke it when the review is done."}
            </p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Expires after</Label>
              <Select value={days} onValueChange={setDays}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EXPIRY.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {config && (
              <div className="space-y-2">
                <Label>Language</Label>
                <Select value={lang} onValueChange={setLang}>
                  <SelectTrigger className="w-full">
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
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="share-note">
                Note{" "}
                <span className="font-normal text-muted-foreground">
                  (optional, only staff see it)
                </span>
              </Label>
              <Input
                id="share-note"
                value={note}
                placeholder="For example: for the client"
                onChange={(event) => setNote(event.target.value)}
              />
            </div>
          </div>
        )}
        {others.length > 0 && (
          <div className="space-y-2">
            <Label>Active links</Label>
            <ul className="divide-y rounded-lg border">
              {others.map((link) => (
                <li
                  key={link.id}
                  className="flex items-center gap-3 px-3 py-2 text-sm"
                >
                  <PiLinkBold className="size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">
                      {link.note || "Draft link"}
                      {link.language && config && (
                        <span className="ml-1.5 text-xs font-normal text-muted-foreground uppercase">
                          {link.language}
                        </span>
                      )}
                    </div>
                    <div
                      className={cn("truncate text-xs text-muted-foreground")}
                    >
                      {describe(link)}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    onClick={() => revoke(link.id)}
                  >
                    Revoke
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
        <DialogFooter>
          {created ? (
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button disabled={isPending} onClick={() => create()}>
                Create link
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
