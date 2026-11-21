import { useMutation, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { useTranslation } from "react-i18next";
import {
  PiArrowLeftBold,
  PiArrowSquareOutBold,
  PiCheckBold,
  PiDotsThreeBold,
} from "react-icons/pi";
import { toast } from "sonner";

import {
  FollowButton,
  FollowMenuItem,
} from "@/components/notifications/follow-button";
import { PresenceAvatars } from "@/components/presence";
import { PublishButton } from "@/components/publishing/publish-button";
import {
  usePublishing,
  useShowPublishButton,
} from "@/components/publishing/publishing";
import { PublishingBadge } from "@/components/publishing/publishing-badge";
import { Button } from "@/components/ui/button";
import { DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PageHeader } from "@/components/ui/page-header";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAdminInfo } from "@/hooks/use-admin-info";
import useConfirmDialog from "@/hooks/use-confirm-dialog";
import { useHttp } from "@/hooks/use-http";
import { useRunAction } from "@/hooks/use-run-action";
import { isSafeHref } from "@/lib/html";
import { formatKeptAt } from "@/lib/recovery";
import { cn, getErrorMessage } from "@/lib/utils";
import type {
  DateTimeString,
  FormField,
  Model,
  PresenceUser,
  Resource,
} from "@/types";

import { Conditional } from "./conditional";
import {
  LanguageBar,
  LanguageMenu,
  LanguageSwitcher,
  languageUi,
  useLanguageStates,
} from "./content-language";
import { ComponentRenderer } from "./form-field";
import { SaveButton, type SaveMode } from "./save-button";
import { SetPasswordDialog } from "./set-password-dialog";

export function Header({
  model,
  resource,
  resourcePath,
  isSaving,
  dialog = false,
  components = model?.admin.edit.header ?? [],
  readOnly = false,
  canDelete = true,
  presence = [],
  keptAt = null,
  saveOptions = {},
  onDuplicate,
  onSave,
  onDelete,
  onClose,
}: {
  model: Model;
  resource?: Resource;
  resourcePath: string;
  isSaving: boolean;
  // The edit_header components; defaults to the model's studio
  // (inline rows pass their inline's).
  components?: FormField[];
  // Read-only editors have no save button.
  readOnly?: boolean;
  canDelete?: boolean;
  // The other users who have the object open.
  presence?: PresenceUser[];
  // When the unsaved changes were last kept in this browser.
  keptAt?: number | null;
  // The Save menu's options: save and add another, save and close.
  // The button does the editor's default save action.
  saveOptions?: {
    addAnother?: boolean;
    close?: boolean;
    defaultMode?: SaveMode;
  };
  // Offers Duplicate in the more actions menu.
  onDuplicate?: VoidFunction;
  // Whether the editor renders inside a Dialog: the title then is a
  // DialogTitle and the close button confirms unsaved changes itself;
  // routed editors rely on the navigation guard instead.
  dialog?: boolean;
  onSave(mode?: SaveMode): Promise<void>;
  onDelete?: VoidFunction;
  onClose?: VoidFunction;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const { data: info } = useAdminInfo();
  const confirm = useConfirmDialog();
  const form = useFormContext();
  const isCreate = !resource?.id;
  const isSingleton = model?.admin.is_singleton ?? false;
  // Follow, with the notifications app; not in dialogs (inline rows and
  // related objects are followed through their own pages).
  const canFollow =
    !!model?.admin.notifications && !dialog && !isCreate && !!resource;
  const showDuplicate = !isSingleton && !!onDuplicate;
  const showDelete = !isSingleton && canDelete;
  // Users: an admin sets another user's password.
  const showSetPassword =
    !dialog && !isCreate && !!resource?.__user__?.can_set_password;
  const [setPasswordOpen, setSetPasswordOpen] = useState(false);
  // Users: an admin emails a link to set the password (an invite when
  // the user never logged in).
  const showSendLink =
    !dialog && !isCreate && !!resource?.__user__?.can_send_password_link;
  const invited = !!resource?.__user__?.invited;
  const { mutateAsync: sendLink } = useMutation({
    async mutationFn(id: string) {
      const { data } = await http.post<{ email: string }>(
        `${resourcePath}/${id}/password-link`,
      );
      return data;
    },
  });
  // Users: an admin resets two-factor login for someone who lost their
  // phone.
  const showResetTwoFactor =
    !dialog && !isCreate && !!resource?.__user__?.can_reset_two_factor;
  const { mutateAsync: resetTwoFactor } = useMutation({
    async mutationFn(id: string) {
      await http.post(`${resourcePath}/${id}/two-factor/reset`);
    },
  });
  const showUserActions = showSetPassword || showSendLink || showResetTwoFactor;
  // The object's public page (the studio's view_on_site), once saved.
  // Only http(s) and relative URLs: a stored javascript: URL would run
  // in the admin (the server drops those too).
  const viewOnSiteUrl =
    !isCreate &&
    resource?.__view_on_site__ &&
    isSafeHref(resource.__view_on_site__)
      ? resource.__view_on_site__
      : null;
  // The studio's edit_actions: @bulk_action methods run on this object.
  const editActions =
    !dialog && !isCreate && !isSingleton
      ? (model?.admin.edit.actions ?? [])
      : [];
  const showEditActions = editActions.length > 0;
  const { runAction, dialog: actionDialog } = useRunAction(model);
  const { isDirty } = form.formState;
  const editedAt =
    resource && info
      ? (resource[info.settings.edited_at_attr] as DateTimeString)
      : null;
  const queryClient = useQueryClient();
  // Content that is not live: Save steps back for Publish.
  const showPublish = useShowPublishButton();
  const publishing = usePublishing();

  // After an edit action the object may have changed: show its new
  // values, unless that would discard the editor's unsaved changes.
  async function refreshObject() {
    if (!resource?.id || form.formState.isDirty) {
      return;
    }

    const { data } = await http.get<Resource>(`${resourcePath}/${resource.id}`);

    form.reset({
      ...data,
      id: data.id != null ? String(data.id) : data.id,
    });
  }

  const { mutateAsync } = useMutation({
    async mutationFn(id: string) {
      await http.delete(`${resourcePath}/${id}`);
    },
    async onSuccess() {
      await queryClient.invalidateQueries({
        queryKey: ["resources", model.label],
      });
    },
  });

  return (
    model && (
      <>
        <DialogHeader className="z-10 block">
          <PageHeader
            heading={dialog ? "div" : "h1"}
            back={
              !isSingleton && (
                <Button
                  size="icon-sm"
                  variant="ghost"
                  className="-ml-2 text-muted-foreground"
                  disabled={isSaving}
                  aria-label={t("editor.back_to_list")}
                  onClick={async () => {
                    if (dialog) {
                      if (!isDirty) {
                        return onClose?.();
                      }

                      const confirmed = await confirm({
                        description: t("editor.unsaved_alert"),
                      });

                      if (confirmed) {
                        onClose?.();
                      }

                      return;
                    }

                    onClose?.();
                  }}
                >
                  <PiArrowLeftBold />
                </Button>
              )
            }
            icon={model.admin.icon && <span className={model.admin.icon} />}
            title={
              <span className="flex items-center gap-1.5 min-w-0">
                {dialog ? (
                  <DialogTitle
                    className={cn(
                      "text-base leading-normal font-medium shrink-0 first-letter:uppercase",
                      resource ? "text-muted-foreground" : "font-semibold",
                    )}
                  >
                    {model.verbose_name_plural}
                  </DialogTitle>
                ) : (
                  <span
                    className={cn(
                      "shrink-0 first-letter:uppercase",
                      resource && "text-muted-foreground font-medium",
                    )}
                  >
                    {model.verbose_name_plural}
                  </span>
                )}
                {resource && (
                  <>
                    <span className="text-muted-foreground/50 shrink-0">/</span>
                    <span className="truncate">{resource.__str__}</span>
                    {publishing && (
                      <PublishingBadge
                        state={publishing.info.state}
                        short
                        className="hidden sm:inline-flex ml-1"
                      />
                    )}
                  </>
                )}
              </span>
            }
            actions={
              <>
                <HeaderLanguageSwitcher />
                <PresenceAvatars users={presence} />
                {canFollow && (
                  <FollowButton
                    model={model}
                    id={resource.id}
                    name={resource.__str__}
                    className="hidden lg:inline-flex"
                  />
                )}
                {isDirty && !readOnly ? (
                  <div className="hidden lg:flex items-center gap-1.5 text-muted-foreground text-sm mr-2 select-none">
                    <span className="size-1.5 rounded-full bg-warning" />
                    {t("editor.unsaved_changes")}
                    {keptAt && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span
                            className="inline-flex text-success"
                            aria-label={t("recovery.kept", {
                              when: formatKeptAt(keptAt),
                            })}
                            data-testid="changes-kept"
                          >
                            <PiCheckBold className="size-3.5" />
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>
                          {t("recovery.kept", { when: formatKeptAt(keptAt) })}
                        </TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                ) : editedAt ? (
                  <div className="hidden lg:block text-muted-foreground text-sm mr-2 select-none">
                    {`${t("editor.last_edited")} ${dayjs(editedAt).fromNow()}`}
                  </div>
                ) : null}
                {viewOnSiteUrl && (
                  <Button
                    asChild
                    variant="outline"
                    className="max-lg:w-8 max-lg:px-0"
                  >
                    <a
                      href={viewOnSiteUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <PiArrowSquareOutBold />
                      <span className="sr-only lg:not-sr-only">
                        {t("editor.view_on_site")}
                      </span>
                    </a>
                  </Button>
                )}
                {components.map((component) => (
                  <Conditional
                    key={component.component_id}
                    when={component.when}
                  >
                    <ComponentRenderer formField={component} model={model} />
                  </Conditional>
                ))}
                {!isCreate &&
                  (showDelete ||
                    showDuplicate ||
                    showUserActions ||
                    showEditActions ||
                    canFollow) && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={t("editor.more_actions")}
                          // Only Follow inside: the header shows it wide.
                          className={cn(
                            !showDelete &&
                              !showDuplicate &&
                              !showSetPassword &&
                              !showEditActions &&
                              "lg:hidden",
                          )}
                        >
                          <PiDotsThreeBold />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {canFollow && (
                          <FollowMenuItem
                            model={model}
                            id={resource.id}
                            name={resource.__str__}
                            className="lg:hidden"
                          />
                        )}
                        {editActions.map((action) => (
                          <DropdownMenuItem
                            key={action.id}
                            variant={
                              action.destructive ? "destructive" : "default"
                            }
                            className="justify-start"
                            onSelect={() =>
                              runAction(action, [String(resource!.id)], {
                                name: resource!.__str__,
                                onDone: refreshObject,
                              })
                            }
                          >
                            {action.icon && (
                              <span className={cn(action.icon, "text-sm")} />
                            )}
                            {action.label}
                          </DropdownMenuItem>
                        ))}
                        {showEditActions &&
                          (showDuplicate || showUserActions) && (
                            <DropdownMenuSeparator />
                          )}
                        {showDuplicate && (
                          <DropdownMenuItem onSelect={onDuplicate!}>
                            {t("editor.duplicate")}
                          </DropdownMenuItem>
                        )}
                        {showSetPassword && (
                          <DropdownMenuItem
                            onSelect={() => setSetPasswordOpen(true)}
                          >
                            {t("users.set_password.menu")}
                          </DropdownMenuItem>
                        )}
                        {showSendLink && (
                          <DropdownMenuItem
                            onSelect={async () => {
                              const confirmed = await confirm({
                                title: t(
                                  invited
                                    ? "users.send_link.invite_title"
                                    : "users.send_link.title",
                                ),
                                description: t(
                                  invited
                                    ? "users.send_link.invite_description"
                                    : "users.send_link.description",
                                  { name: resource.__str__ },
                                ),
                                okText: t("users.send_link.send"),
                              });

                              if (!confirmed) {
                                return;
                              }

                              try {
                                const { email } = await sendLink(
                                  String(resource.id),
                                );
                                toast.success(
                                  t(
                                    invited
                                      ? "users.send_link.invite_sent"
                                      : "users.send_link.sent",
                                    { email },
                                  ),
                                );
                              } catch (e: unknown) {
                                toast.error(getErrorMessage(e));
                              }
                            }}
                          >
                            {t(
                              invited
                                ? "users.send_link.invite_menu"
                                : "users.send_link.menu",
                            )}
                          </DropdownMenuItem>
                        )}
                        {showResetTwoFactor && (
                          <DropdownMenuItem
                            onSelect={async () => {
                              const confirmed = await confirm({
                                title: t("users.reset_two_factor.title"),
                                description: t(
                                  "users.reset_two_factor.description",
                                  { name: resource.__str__ },
                                ),
                                okText: t("users.reset_two_factor.reset"),
                              });

                              if (!confirmed) {
                                return;
                              }

                              try {
                                await resetTwoFactor(String(resource.id));
                                await queryClient.invalidateQueries({
                                  queryKey: ["resources", model.label],
                                });
                                toast.success(
                                  t("users.reset_two_factor.done", {
                                    name: resource.__str__,
                                  }),
                                );
                              } catch (e: unknown) {
                                toast.error(getErrorMessage(e));
                              }
                            }}
                          >
                            {t("users.reset_two_factor.menu")}
                          </DropdownMenuItem>
                        )}
                        {(showDuplicate ||
                          showUserActions ||
                          showEditActions) &&
                          showDelete && <DropdownMenuSeparator />}
                        {showDelete && (
                          <DropdownMenuItem
                            className="text-destructive"
                            onSelect={async () => {
                              const confirmed = await confirm({
                                title: t("common.delete_confirm_title"),
                                // With soft delete the object lands in the
                                // trash and can be restored, which the
                                // regular message denies.
                                description: t(
                                  model.admin.list.trash
                                    ? "common.delete_to_trash_confirm_description"
                                    : "common.delete_confirm_description",
                                ),
                              });

                              if (!confirmed) {
                                return;
                              }

                              // A refused delete (objects that refer to it,
                              // or the studio's delete_model) keeps the page
                              // open and says why.
                              try {
                                await mutateAsync(resource!.id);
                              } catch (e: unknown) {
                                toast.error(getErrorMessage(e));
                                return;
                              }

                              onDelete?.();
                            }}
                          >
                            {t("common.delete")}
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                {!readOnly && (
                  <SaveButton
                    create={isCreate && !isSingleton}
                    isSaving={isSaving}
                    addAnother={saveOptions.addAnother}
                    close={saveOptions.close}
                    defaultMode={saveOptions.defaultMode}
                    outline={showPublish}
                    onSave={async (mode) => {
                      try {
                        await onSave(mode);
                      } catch {
                        // Errors are already surfaced by the save flow.
                      }
                    }}
                  />
                )}
                <PublishButton disabled={isSaving} />
              </>
            }
          />
          <HeaderLanguageBar />
        </DialogHeader>
        {showSetPassword && (
          <SetPasswordDialog
            open={setPasswordOpen}
            onOpenChange={setSetPasswordOpen}
            resourcePath={resourcePath}
            id={String(resource.id)}
            name={resource.__str__}
          />
        )}
        {actionDialog}
      </>
    )
  );
}

function HeaderLanguageSwitcher() {
  const states = useLanguageStates();
  const ui = languageUi();

  return ui === "menu" ? (
    <LanguageMenu states={states} />
  ) : ui === "bar" ? null : (
    <LanguageSwitcher states={states} className="mr-1" />
  );
}

function HeaderLanguageBar() {
  const states = useLanguageStates();

  return languageUi() === "bar" ? <LanguageBar states={states} /> : null;
}
