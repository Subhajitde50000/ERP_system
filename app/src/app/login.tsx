/**
 * Login — mobile port of fontend/app/(auth)/login/page.tsx +
 * components/auth/login-form.tsx. Same layout as the website on a phone:
 * gradient mobile banner on top, then the "Welcome back" card.
 *
 * The website resolves the institution from the subdomain; the app asks for
 * the institution code (slug) directly, because that field is what the same
 * login endpoint requires.
 */

import { useEffect, useState } from "react";
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeftRight, ArrowRight, Building2, Check } from "lucide-react-native";

import { MobileBanner } from "@/components/brand-banner";
import { Button } from "@/components/button";
import { FormAlert } from "@/components/form-alert";
import { TextField } from "@/components/text-field";
import { AuthError, ERROR_MESSAGES, MIN_PASSWORD_LENGTH, login, logout } from "@/lib/auth";
import { consoleHref, isTeacherRole } from "@/lib/roles";
import { useInstitutionAuth } from "@/lib/session";
import { Colors } from "@/theme";

type Status =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "error"; message: string }
  | { kind: "success"; message: string };

export default function LoginScreen() {
  const router = useRouter();
  const { setUserFromLogin, institutionSlug, isLoading } = useInstitutionAuth();
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [fieldErrors, setFieldErrors] = useState<{
    identifier?: string;
    password?: string;
  }>({});

  const submitting = status.kind === "submitting";
  const succeeded = status.kind === "success";

  useEffect(() => {
    if (!isLoading && !institutionSlug) {
      router.replace("/institution");
    }
  }, [isLoading, institutionSlug, router]);

  async function handleSubmit() {
    if (submitting || succeeded) return;

    if (!institutionSlug) {
      router.replace("/institution");
      return;
    }

    // Client-side validation before hitting the network
    const errors: typeof fieldErrors = {};
    if (!identifier.trim()) errors.identifier = "Enter your email or roll number";
    if (!password) errors.password = "Enter your password";
    else if (password.length < MIN_PASSWORD_LENGTH)
      errors.password = "Password must be at least 6 characters";

    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      setStatus({ kind: "idle" });
      return;
    }

    setStatus({ kind: "submitting" });

    try {
      const result = await login({
        identifier: identifier.trim(),
        password,
        remember,
        tenantId: institutionSlug.trim(),
      });

      const home = consoleHref(result.roles);
      if (!home) {
        await logout().catch(() => undefined);
        setStatus({
          kind: "error",
          message:
            "This app is for student and teacher accounts. Sign in with those credentials, or use the website for other roles.",
        });
        return;
      }

      // Hydrate the session from the login response so the console gate opens.
      setUserFromLogin({
        id: result.user.id,
        name: result.user.name,
        email: result.user.email || null,
        tenantId: institutionSlug.trim(),
        roles: result.roles,
      });

      setStatus({
        kind: "success",
        message: isTeacherRole(result.roles)
          ? "Signed in as Teacher — redirecting…"
          : "Signed in as Student — redirecting…",
      });
      setTimeout(() => router.replace(home), 600);
    } catch (err) {
      const message =
        err instanceof AuthError
          ? err.message || ERROR_MESSAGES[err.code]
          : ERROR_MESSAGES.UNKNOWN;
      setStatus({ kind: "error", message });
    }
  }

  function handleContactAdmin() {
    Alert.alert(
      "Contact Institution Admin",
      "Your Institution Admin is your school or college IT administrator, Registrar, or Academic Office.\n\n• If you need your Institution Code, check your admission confirmation email or portal URL (e.g. abc-college.shikshasync.me).\n• If you cannot access your account or reset your password, contact your campus helpdesk or teacher to reset it directly.",
      [{ text: "Got it" }]
    );
  }

  function handleChangeInstitution() {
    router.push("/institution");
  }

  return (
    <View style={styles.screen}>
      <MobileBanner />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.main}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.cardWrap}>
            <View style={styles.card}>
              <View style={styles.heading}>
                <Text style={styles.h1}>Welcome back</Text>
                <Text style={styles.subtitle}>Sign in to your institution account</Text>
                {institutionSlug ? (
                  <View style={styles.institutionPill}>
                    <Building2 size={14} color={Colors.accent} />
                    <Text style={styles.institutionPillText}>{institutionSlug}</Text>
                  </View>
                ) : null}
              </View>

              {status.kind === "error" ? (
                <View style={styles.alertGap}>
                  <FormAlert variant="error">{status.message}</FormAlert>
                </View>
              ) : null}

              {succeeded ? (
                <View style={styles.alertGap}>
                  <FormAlert variant="success">{status.message}</FormAlert>
                </View>
              ) : null}

              <View style={styles.form}>
                <TextField
                  label="Email or Roll Number"
                  placeholder="you@college.edu or ROLL123"
                  value={identifier}
                  onChangeText={(value) => {
                    setIdentifier(value);
                    setFieldErrors((p) => ({ ...p, identifier: undefined }));
                  }}
                  error={fieldErrors.identifier}
                  editable={!submitting && !succeeded}
                />

                <TextField
                  label="Password"
                  placeholder="••••••••"
                  value={password}
                  onChangeText={(value) => {
                    setPassword(value);
                    setFieldErrors((p) => ({ ...p, password: undefined }));
                  }}
                  error={fieldErrors.password}
                  revealable
                  editable={!submitting && !succeeded}
                  labelAction={
                    <TouchableOpacity
                      onPress={() => router.push("/forgot-password")}
                      disabled={submitting || succeeded}
                      accessibilityRole="button"
                    >
                      <Text style={styles.forgotLink}>Forgot?</Text>
                    </TouchableOpacity>
                  }
                />

                <Pressable
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: remember }}
                  onPress={() => !submitting && !succeeded && setRemember((v) => !v)}
                  style={styles.rememberRow}
                >
                  <View style={[styles.checkbox, remember && styles.checkboxChecked]}>
                    {remember ? <Check size={12} color="#FFFFFF" strokeWidth={3} /> : null}
                  </View>
                  <Text style={styles.rememberLabel}>Remember me for 7 days</Text>
                </Pressable>

                <Button
                  loading={submitting}
                  loadingText="Signing in…"
                  disabled={succeeded}
                  onPress={handleSubmit}
                >
                  <Text style={styles.buttonLabel}>{succeeded ? "Redirecting…" : "Sign in"}</Text>
                  {!succeeded ? <ArrowRight size={16} color="#FFFFFF" /> : null}
                </Button>

                <View style={styles.divider} />

                {/* Bottom option to change Institution code */}
                <View style={styles.bottomActions}>
                  <TouchableOpacity
                    style={styles.changeInstitutionButton}
                    onPress={handleChangeInstitution}
                    disabled={submitting || succeeded}
                    accessibilityRole="button"
                  >
                    <ArrowLeftRight size={14} color={Colors.accent} />
                    <Text style={styles.changeInstitutionText}>
                      Change Institution <Text style={styles.changeInstitutionCode}>({institutionSlug || "None"})</Text>
                    </Text>
                  </TouchableOpacity>

                  <Text style={styles.help}>
                    Having trouble?{" "}
                    <Text
                      style={styles.helpLink}
                      onPress={handleContactAdmin}
                      accessibilityRole="button"
                    >
                      Contact Institution Admin
                    </Text>
                  </Text>
                </View>
              </View>
            </View>

            <Text style={styles.footer}>
              Protected by tenant isolation · All logins are audited ·{" "}
              <Text style={styles.footerVersion}>v0.1.0</Text>
            </Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  flex: {
    flex: 1,
  },
  main: {
    flexGrow: 1,
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    padding: 24,
  },
  cardWrap: {
    width: "100%",
    maxWidth: 400,
  },
  card: {
    backgroundColor: "#FFFFFF",
  },
  heading: {
    marginBottom: 24,
  },
  h1: {
    fontSize: 22,
    fontWeight: "700",
    color: "#0F172A",
  },
  subtitle: {
    marginTop: 4,
    fontSize: 13,
    color: "#64748B",
  },
  institutionPill: {
    marginTop: 10,
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 4,
    paddingHorizontal: 10,
    backgroundColor: "rgba(79, 70, 229, 0.08)",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(79, 70, 229, 0.2)",
  },
  institutionPillText: {
    fontSize: 13,
    fontWeight: "600",
    color: Colors.accent,
  },
  alertGap: {
    marginBottom: 20,
  },
  form: {
    gap: 16,
  },
  rememberRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 4,
  },
  checkbox: {
    width: 16,
    height: 16,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: "#CBD5E1",
    backgroundColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center",
  },
  checkboxChecked: {
    backgroundColor: Colors.accent,
    borderColor: Colors.accent,
  },
  rememberLabel: {
    fontSize: 13,
    color: "#475569",
  },
  buttonLabel: {
    fontSize: 14,
    fontWeight: "600",
    color: "#FFFFFF",
  },
  divider: {
    height: 1,
    backgroundColor: "#F1F5F9",
    marginVertical: 4,
  },
  bottomActions: {
    gap: 12,
    alignItems: "center",
  },
  changeInstitutionButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 8,
    backgroundColor: "#F8FAFC",
    borderWidth: 1,
    borderColor: "#E2E8F0",
  },
  changeInstitutionText: {
    fontSize: 13,
    fontWeight: "500",
    color: "#334155",
  },
  changeInstitutionCode: {
    fontWeight: "600",
    color: Colors.accent,
  },
  help: {
    textAlign: "center",
    fontSize: 12,
    color: "#64748B",
  },
  helpLink: {
    fontWeight: "600",
    color: Colors.accent,
  },
  forgotLink: {
    fontSize: 12,
    fontWeight: "600",
    color: Colors.accent,
  },
  footer: {
    marginTop: 24,
    textAlign: "center",
    fontSize: 11,
    lineHeight: 16,
    color: "#475569",
  },
  footerVersion: {
    fontWeight: "500",
    color: "#0F172A",
  },
});
