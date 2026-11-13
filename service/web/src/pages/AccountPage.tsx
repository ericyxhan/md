import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, UserCog } from "lucide-react";
import * as api from "../lib/api";
import { useAuth } from "../auth/AuthProvider";
import { PageHeader } from "../components/layout/PageHeader";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Field, TextInput } from "../components/ui/Form";

interface Details {
  firstName: string;
  lastName: string;
  email: string;
}

const EMPTY: Details = { firstName: "", lastName: "", email: "" };

export function AccountPage() {
  const { user, refresh } = useAuth();
  const queryClient = useQueryClient();

  const [details, setDetails] = useState<Details>(EMPTY);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");

  const [profileNotice, setProfileNotice] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [passwordNotice, setPasswordNotice] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  // The account arrives with the session, which is read asynchronously, so
  // the form cannot be seeded from it at mount.  It is filled in when the
  // account turns up, and refilled from the server's answer after a save so
  // that a normalized address is shown the way it was stored.
  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!user || loadedFor.current === user.id) return;
    loadedFor.current = user.id;
    setDetails({
      firstName: user.first_name,
      lastName: user.last_name,
      email: user.email,
    });
  }, [user]);

  const saveProfile = useMutation({
    mutationFn: () =>
      api.updateMe({
        first_name: details.firstName.trim(),
        last_name: details.lastName.trim(),
        email: details.email.trim(),
      }),
    onSuccess: async (updated) => {
      setDetails({
        firstName: updated.first_name,
        lastName: updated.last_name,
        email: updated.email,
      });
      setProfileError(null);
      setProfileNotice("Your details were saved.");
      // The session carries the account details, so it has to be re-read
      // for the sidebar and the header to show the new name.
      await refresh();
      await queryClient.invalidateQueries();
    },
    onError: (error) => {
      setProfileNotice(null);
      setProfileError(
        error instanceof Error ? error.message : "The change was rejected.",
      );
    },
  });

  const changePassword = useMutation({
    mutationFn: () =>
      api.updateMe({
        password: newPassword,
        current_password: currentPassword,
      }),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmation("");
      setPasswordError(null);
      setPasswordNotice("Your password was changed.");
    },
    onError: (error) => {
      setPasswordNotice(null);
      setPasswordError(
        error instanceof Error ? error.message : "The change was rejected.",
      );
    },
  });

  const submitProfile = (event: FormEvent) => {
    event.preventDefault();
    if (!details.firstName.trim() || !details.lastName.trim() || !details.email.trim())
      return;
    setProfileNotice(null);
    setProfileError(null);
    saveProfile.mutate();
  };

  const submitPassword = (event: FormEvent) => {
    event.preventDefault();
    if (!currentPassword || !newPassword) return;
    if (newPassword !== confirmation) {
      setPasswordError("The two passwords do not match");
      return;
    }
    setPasswordNotice(null);
    setPasswordError(null);
    changePassword.mutate();
  };

  return (
    <div>
      <PageHeader
        eyebrow="Your account"
        title="Account"
        description="Your name, your email address, and your password. Everything you run on this server belongs to this account."
      />

      <Card className="mt-6">
        <CardHeader
          title="Details"
          description="The name and address other people see for your work."
        />
        <CardBody>
          <form onSubmit={submitProfile} className="max-w-lg space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="First name" htmlFor="account-first-name">
                <TextInput
                  id="account-first-name"
                  value={details.firstName}
                  onChange={(event) =>
                    setDetails((current) => ({
                      ...current,
                      firstName: event.target.value,
                    }))
                  }
                  autoComplete="given-name"
                />
              </Field>
              <Field label="Last name" htmlFor="account-last-name">
                <TextInput
                  id="account-last-name"
                  value={details.lastName}
                  onChange={(event) =>
                    setDetails((current) => ({
                      ...current,
                      lastName: event.target.value,
                    }))
                  }
                  autoComplete="family-name"
                />
              </Field>
            </div>

            <Field
              label="Email address"
              htmlFor="account-email"
              hint="This is the address you sign in with."
            >
              <TextInput
                id="account-email"
                type="email"
                value={details.email}
                onChange={(event) =>
                  setDetails((current) => ({
                    ...current,
                    email: event.target.value,
                  }))
                }
                autoComplete="email"
              />
            </Field>

            {profileNotice ? (
              <p className="rounded-lg bg-brand-50 px-3 py-2 text-[13px] font-medium text-brand-800 ring-1 ring-inset ring-brand-200/70">
                {profileNotice}
              </p>
            ) : null}
            {profileError ? (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-[13px] font-medium text-rose-700 ring-1 ring-inset ring-rose-200/70">
                {profileError}
              </p>
            ) : null}

            <Button
              type="submit"
              variant="primary"
              loading={saveProfile.isPending}
              leadingIcon={<UserCog className="size-4" />}
            >
              Save details
            </Button>
          </form>
        </CardBody>
      </Card>

      <Card className="mt-5">
        <CardHeader
          title="Password"
          description="Changing your password needs the current one, so a stolen session cannot lock you out."
        />
        <CardBody>
          <form onSubmit={submitPassword} className="max-w-lg space-y-4">
            <Field label="Current password" htmlFor="account-current-password">
              <TextInput
                id="account-current-password"
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                autoComplete="current-password"
              />
            </Field>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label="New password"
                htmlFor="account-new-password"
                hint="At least 10 characters."
              >
                <TextInput
                  id="account-new-password"
                  type="password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  autoComplete="new-password"
                />
              </Field>
              <Field label="Confirm new password" htmlFor="account-confirm-password">
                <TextInput
                  id="account-confirm-password"
                  type="password"
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  autoComplete="new-password"
                />
              </Field>
            </div>

            {passwordNotice ? (
              <p className="rounded-lg bg-brand-50 px-3 py-2 text-[13px] font-medium text-brand-800 ring-1 ring-inset ring-brand-200/70">
                {passwordNotice}
              </p>
            ) : null}
            {passwordError ? (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-[13px] font-medium text-rose-700 ring-1 ring-inset ring-rose-200/70">
                {passwordError}
              </p>
            ) : null}

            <Button
              type="submit"
              variant="secondary"
              loading={changePassword.isPending}
              leadingIcon={<KeyRound className="size-4" />}
              disabled={!currentPassword || !newPassword}
            >
              Change password
            </Button>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
