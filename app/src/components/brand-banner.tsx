/**
 * Mobile top banner — port of fontend/components/auth/mobile-banner.tsx
 * (design §5). The website's radial brand gradient and 5% dot pattern are
 * reproduced with the already-installed react-native-svg.
 */

import { StyleSheet, Text, View } from "react-native";
import { GraduationCap } from "lucide-react-native";
import Svg, { Circle, Defs, RadialGradient, Rect, Stop } from "react-native-svg";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Colors } from "@/theme";

const DOT_STEP = 20;

export function MobileBanner() {
  const insets = useSafeAreaInsets();
  const width = 420; // wide enough for any phone; SVG scales
  const height = 150;
  const dots = [];
  for (let x = 10; x < width; x += DOT_STEP) {
    for (let y = 10; y < height; y += DOT_STEP) {
      dots.push(<Circle key={`${x}-${y}`} cx={x} cy={y} r={1} fill="#FFFFFF" />);
    }
  }

  return (
    <View style={[styles.banner, { paddingTop: insets.top + 32 }]}>
      <Svg style={StyleSheet.absoluteFill} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid slice">
        <Defs>
          {/* radial-gradient(120% 120% at 0% 0%, #4f46e5 0%, #0f172a 60%) */}
          <RadialGradient id="brand" cx="0" cy="0" r="1.2" fx="0" fy="0">
            <Stop offset="0%" stopColor="#4F46E5" />
            <Stop offset="60%" stopColor="#0F172A" />
            <Stop offset="100%" stopColor="#0F172A" />
          </RadialGradient>
        </Defs>
        <Rect x={0} y={0} width={width} height={height} fill="url(#brand)" />
      </Svg>
      <Svg style={[StyleSheet.absoluteFill, styles.dots]} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid slice">
        {dots}
      </Svg>

      <View style={styles.content}>
        <View style={styles.logo}>
          <View style={styles.logoBox}>
            <GraduationCap size={20} color={Colors.primary} />
          </View>
          <Text style={styles.wordmark}>shikshasync.me</Text>
        </View>
        <Text style={styles.slogan}>
          One Platform for <Text style={styles.sloganAccent}>Your Entire Institution</Text>
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: Colors.primary,
    paddingHorizontal: 24,
    paddingBottom: 28,
    overflow: "hidden",
  },
  dots: {
    opacity: 0.05,
  },
  content: {
    zIndex: 10,
  },
  logo: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  logoBox: {
    width: 36,
    height: 36,
    borderRadius: 12,
    backgroundColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center",
  },
  wordmark: {
    fontSize: 20,
    fontWeight: "700",
    letterSpacing: -0.4,
    color: "#FFFFFF",
  },
  slogan: {
    marginTop: 16,
    maxWidth: 320,
    fontSize: 19,
    fontWeight: "700",
    lineHeight: 26,
    color: "#FFFFFF",
  },
  sloganAccent: {
    color: Colors.accentSoft,
  },
});
