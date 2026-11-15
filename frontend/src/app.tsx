import "./index.css";
import "./i18n";
// Dayjs locales: one for each of the admin's languages.
import "dayjs/locale/de";
import "dayjs/locale/en";
import "dayjs/locale/es";
import "dayjs/locale/fr";
import "dayjs/locale/it";
import "dayjs/locale/nl";
import "dayjs/locale/pt-br";

import dayjs from "dayjs";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

import { ConfirmDialogProvider } from "@/components/confirm-dialog-provider";
import { LoadingBar } from "@/components/loading-bar";
import { Toaster } from "@/components/ui/sonner";
import { ValueDialogProvider } from "@/components/value-dialog-provider";
import { Error } from "@/error";
import { useAdminInfo } from "@/hooks/use-admin-info";

export function App() {
  const { i18n } = useTranslation();
  const { isError, error } = useAdminInfo();

  useEffect(() => {
    // Dayjs knows "pt-BR" as "pt-br".
    dayjs.locale(i18n.language.toLowerCase());
  }, [i18n.language]);

  return (
    <>
      <LoadingBar />
      <ConfirmDialogProvider>
        <ValueDialogProvider>
          {isError ? <Error error={error} /> : <Outlet />}
        </ValueDialogProvider>
      </ConfirmDialogProvider>
      <Toaster />
    </>
  );
}
