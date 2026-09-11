/**
 * Institution Setup — Onboarding screen where the user enters their Institution Code
 * for the first time before proceeding to the login screen.
 */

import { useEffect, useState } from "react";
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { ArrowRight, Building2, HelpCircle } from "lucide-react-native";

import { MobileBanner } from "@/components/brand-banner";
import { Button } from "@/components/button";
import { FormAlert } from "@/components/form-alert";
import { TextField } from "@/components/text-field";
import { useInstitutionAuth } from "@/lib/session";
import { Colors } from "@/theme";

export default function InstitutionScreen() {
  const router = useRouter();
  const { institutionSlug, setInstitutionSlug, isAuthenticated } = useInstitutionAuth();
  const [code, setCode] = useState(institutionSlug ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (institutionSlug && !code) {
      setCode(institutionSlug);
    }
  }, [institutionSlug]);

  async function handleContinue() {
    const cleaned = code.trim().toLowerCase();
    if (!cleaned) {
      setError("Please enter your institution code");
      return;
    }

    if (cleaned.length < 2) {
      setError("Institution code is too short");
      return;
    }

    // Slug format: alphanumeric + hyphens
    if (!/^[a-z0-9-]+$/.test(cleaned)) {
      setError("Institution code can only contain letters, numbers, and hyphens");
      return;
    }

    setError(null);
    setSubmitting(true);

    try {
      await setInstitutionSlug(cleaned);
      setSubmitting(false);
      router.replace("/login");
    } catch {
      setSubmitting(false);
      setError("Could not save institution code. Please try again.");
    }
  }

  function handleContactAdmin() {
    Alert.alert(
      "Find Your Institution Code",
      "Your Institution Code is the unique identifier for your campus.\n\n• Check your institution's web portal address: if it is https://green-college.shikshasync.me, your code is 'green-college'.\n• Check your admission letter or welcome email.\n• Contact your campus IT helpdesk or student office for assistance.",
      [{ text: "Got it" }]
    );
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
              <View style={styles.iconCircle}>
                <Building2 size={24} color={Colors.accent} />
              </View>

              <View style={styles.heading}>
                <Text style={styles.h1}>Select your institution</Text>
                <Text style={styles.subtitle}>
                  Enter the institution code provided by your school, college, or university to get started.
                </Text>
              </View>

              {error ? (
                <View style={styles.alertGap}>
                  <FormAlert variant="error">{error}</FormAlert>
                </View>
              ) : null}

              <View style={styles.form}>
                <TextField
                  label="Institution code"
                  placeholder="e.g. green-college"
                  hint="The unique code from your campus or web portal (e.g. abc-college)"
                  value={code}
                  onChangeText={(val) => {
                    setCode(val);
                    setError(null);
                  }}
                  error={error}
                  autoCapitalize="none"
                  editable={!submitting}
                />

                <Button
                  loading={submitting}
                  loadingText="Setting institution…"
                  onPress={handleContinue}
                >
                  <Text style={styles.buttonLabel}>Continue</Text>
                  <ArrowRight size={16} color="#FFFFFF" />
                </Button>

                {institutionSlug ? (
                  <TouchableOpacity
                    style={styles.cancelRow}
                    onPress={() => router.replace("/login")}
                    accessibilityRole="button"
                  >
                    <Text style={styles.cancelText}>Back to Sign in</Text>
                  </TouchableOpacity>
                ) : null}

                <TouchableOpacity
                  style={styles.helpRow}
                  onPress={handleContactAdmin}
                  accessibilityRole="button"
                >
                  <HelpCircle size={15} color={Colors.accent} />
                  <Text style={styles.helpLink}>Need help finding your code?</Text>
                </TouchableOpacity>
              </View>
            </View>

            <Text style={styles.footer}>
              Multi-tenant campus portal · Secure campus isolation ·{" "}
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
  iconCircle: {
    width: 46,
    height: 46,
    borderRadius: 12,
    backgroundColor: "rgba(79, 70, 229, 0.1)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
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
    marginTop: 6,
    fontSize: 13,
    lineHeight: 19,
    color: "#64748B",
  },
  alertGap: {
    marginBottom: 20,
  },
  form: {
    gap: 16,
  },
  buttonLabel: {
    fontSize: 14,
    fontWeight: "600",
    color: "#FFFFFF",
  },
  cancelRow: {
    alignItems: "center",
    paddingVertical: 4,
  },
  cancelText: {
    fontSize: 13,
    fontWeight: "500",
    color: "#64748B",
  },
  helpRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingTop: 10,
  },
  helpLink: {
    fontSize: 13,
    fontWeight: "600",
    color: Colors.accent,
  },
  footer: {
    marginTop: 32,
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
