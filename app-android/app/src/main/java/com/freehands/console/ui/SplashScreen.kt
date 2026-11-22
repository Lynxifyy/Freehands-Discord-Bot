package com.freehands.console.ui

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.abs
import kotlin.math.sin
import kotlin.random.Random

/**
 * The opening shot.
 *
 * A battlefield drawn entirely in Compose: three layers of depth (far haze,
 * mid battle, foreground silhouettes), robot silhouettes with lit optics, and a
 * colossal Freehands mark standing behind the fight. The camera dollies in on
 * that mark over the whole splash, so the eye is pulled from the skirmish to
 * the brand.
 *
 * Drawing it rather than shipping a bitmap keeps the APK small, keeps it sharp
 * at every density, and lets the parallax be real: each layer moves at its own
 * rate, which a single image cannot do.
 */
private object Scene {
    // Sky, horizon and ground. A warm-to-cold vertical ramp reads as dusk
    // without needing a gradient mesh.
    val skyTop = Color(0xFF06080F)
    val skyMid = Color(0xFF101A2E)
    val skyLow = Color(0xFF2A2039)
    val horizon = Color(0xFF4A2F4A)
    val ground = Color(0xFF0A0C12)

    // Ember light from the fight, and the brand blue from the icon.
    val ember = Color(0xFFFF6B35)
    val emberDim = Color(0xFFB33A16)
    val brandGlow = Color(0xFF5865F2)
    val brandHot = Color(0xFF9BA4FF)
    val optic = Color(0xFF6EF3FF)
}

/** Deterministic noise so the crowd of robots does not reshuffle on recompose. */
private fun jitter(seed: Int, salt: Int): Float {
    val r = Random(seed * 7919 + salt)
    return r.nextFloat()
}

@Composable
fun SplashScreen(onFinished: () -> Unit) {
    // One clock for the whole scene. `camera` runs 0..1 across the splash and
    // drives the dolly; `time` loops forever for the small motions.
    var started by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { started = true }

    val motion = rememberInfiniteTransition(label = "battle")
    val time by motion.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(9000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "time",
    )
    val flicker by motion.animateFloat(
        initialValue = 0.72f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(1400, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "flicker",
    )

    val camera by androidx.compose.animation.core.animateFloatAsState(
        targetValue = if (started) 1f else 0f,
        animationSpec = tween(5200, easing = LinearEasing),
        label = "camera",
    )

    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(2600)
        onFinished()
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    0f to Scene.skyTop,
                    0.38f to Scene.skyMid,
                    0.62f to Scene.skyLow,
                    0.74f to Scene.horizon,
                    1f to Scene.ground,
                )
            )
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val w = size.width
            val h = size.height
            val horizonY = h * 0.70f

            // The camera moves the *world*, not the frame: nearer layers shift
            // and grow more than far ones, which is what sells the depth.
            val push = camera

            drawStars(w, h, horizonY, time)
            drawIcon(w, h, horizonY, push, flicker)
            drawFarBattle(w, h, horizonY, push, time)
            drawMidBattle(w, h, horizonY, push, time, flicker)
            drawGroundGlow(w, h, horizonY, push, flicker)
            drawForeground(w, h, horizonY, push)
            drawVignette(w, h)
        }

        Column(
            Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 54.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                "FREEHANDS",
                color = Color.White.copy(alpha = 0.92f),
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 6.sp,
            )
            Spacer(Modifier.height(5.dp))
            Text(
                "ETERNAL CONSOLE",
                color = Scene.brandHot.copy(alpha = 0.55f),
                fontSize = 9.sp,
                fontFamily = FontFamily.Monospace,
                letterSpacing = 3.sp,
            )
        }
    }
}

/** A cold sky with a few faint stars, dimmed toward the lit horizon. */
private fun DrawScope.drawStars(w: Float, h: Float, horizonY: Float, time: Float) {
    for (i in 0 until 90) {
        val x = jitter(i, 1) * w
        val y = jitter(i, 2) * horizonY * 0.92f
        val twinkle = 0.25f + 0.55f * abs(sin((time * 6.283f) + i))
        val alpha = twinkle * (1f - y / horizonY) * 0.9f
        drawCircle(
            color = Color.White.copy(alpha = alpha.coerceIn(0f, 0.8f)),
            radius = 0.6f + jitter(i, 3) * 1.1f,
            center = Offset(x, y),
        )
    }
}

/**
 * The Freehands mark: a colossal rounded-square badge standing on the horizon.
 *
 * It is drawn in perspective (narrower at the top) and lit from below by the
 * battle, which makes it read as a structure in the world rather than a logo
 * pasted on the sky. The camera ends on it, so it grows and rises as `push`
 * climbs.
 */
private fun DrawScope.drawIcon(
    w: Float,
    h: Float,
    horizonY: Float,
    push: Float,
    flicker: Float,
) {
    val grow = 1f + push * 0.85f
    val cx = w * 0.5f
    val baseY = horizonY - 8f
    val side = h * 0.30f * grow
    val topY = baseY - side
    // Top is 78% of the base width: a mild perspective, not a cartoon trapezoid.
    val halfBottom = side * 0.5f
    val halfTop = halfBottom * 0.78f

    // Halo. Two stacked radial washes: a wide cold one and a tight hot core.
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(Scene.brandGlow.copy(alpha = 0.30f * flicker), Color.Transparent),
            center = Offset(cx, topY + side * 0.45f),
            radius = side * 2.1f,
        ),
        radius = side * 2.1f,
        center = Offset(cx, topY + side * 0.45f),
    )
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(Scene.brandHot.copy(alpha = 0.20f * flicker), Color.Transparent),
            center = Offset(cx, topY + side * 0.45f),
            radius = side * 0.9f,
        ),
        radius = side * 0.9f,
        center = Offset(cx, topY + side * 0.45f),
    )

    // The badge body.
    val body = Path().apply {
        moveTo(cx - halfBottom, baseY)
        lineTo(cx - halfTop, topY)
        lineTo(cx + halfTop, topY)
        lineTo(cx + halfBottom, baseY)
        close()
    }
    drawPath(
        body,
        brush = Brush.verticalGradient(
            0f to Color(0xFF2B3168),
            0.5f to Color(0xFF3D46A8),
            1f to Scene.brandGlow,
            startY = topY,
            endY = baseY,
        ),
    )
    drawPath(body, color = Scene.brandHot.copy(alpha = 0.55f), style = Stroke(width = 2.2f))

    // The mark inside: a stylised open hand - four fingers and a thumb - which
    // is what the real icon shows, abstracted to read at splash size.
    val handCx = cx
    val handBase = baseY - side * 0.20f
    val fingerW = side * 0.075f
    for (i in 0 until 4) {
        val spread = (i - 1.5f) * side * 0.115f
        val height = side * (0.30f + 0.05f * (1.5f - abs(i - 1.5f)))
        val top = handBase - height
        drawRoundRect(
            color = Color.White.copy(alpha = 0.90f),
            topLeft = Offset(handCx + spread - fingerW / 2f, top),
            size = Size(fingerW, height + side * 0.10f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(fingerW * 0.5f),
        )
    }
    // Palm and thumb.
    drawRoundRect(
        color = Color.White.copy(alpha = 0.90f),
        topLeft = Offset(handCx - side * 0.20f, handBase - side * 0.10f),
        size = Size(side * 0.40f, side * 0.22f),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(side * 0.05f),
    )
    drawRoundRect(
        color = Color.White.copy(alpha = 0.90f),
        topLeft = Offset(handCx - side * 0.27f, handBase - side * 0.22f),
        size = Size(side * 0.09f, side * 0.17f),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(side * 0.045f),
    )

    // Contact shadow, so it stands on the ground instead of floating.
    drawOval(
        brush = Brush.radialGradient(
            colors = listOf(Color.Black.copy(alpha = 0.55f), Color.Transparent),
            center = Offset(cx, baseY),
            radius = halfBottom * 1.6f,
        ),
        topLeft = Offset(cx - halfBottom * 1.6f, baseY - side * 0.09f),
        size = Size(halfBottom * 3.2f, side * 0.20f),
    )
}

/**
 * Distant silhouettes: small, low contrast, near the horizon.
 *
 * Parallax is applied as a horizontal drift plus a scale about the horizon, so
 * the far layer barely moves while the near one sweeps past.
 */
private fun DrawScope.drawFarBattle(
    w: Float,
    h: Float,
    horizonY: Float,
    push: Float,
    time: Float,
) {
    val scale = 1f + push * 0.12f
    val drift = -push * w * 0.035f
    translate(left = drift, top = horizonY * (1f - scale)) {
        scale(scale, scale, pivot = Offset(w * 0.5f, horizonY)) {
            for (i in 0 until 14) {
                val x = w * (0.04f + 0.93f * jitter(i, 11)) + sin(time * 6.28f + i) * 2f
                val height = h * (0.055f + 0.030f * jitter(i, 12))
                drawRobot(
                    x = x,
                    footY = horizonY - h * 0.004f,
                    height = height,
                    body = Color(0xFF151A2A),
                    trim = Scene.brandGlow.copy(alpha = 0.20f),
                    optic = Scene.emberDim.copy(alpha = 0.45f),
                    lean = (jitter(i, 13) - 0.5f) * 0.5f,
                )
            }
        }
    }
}

/** The fight: bigger, brighter, with muzzle flashes and lit optics. */
private fun DrawScope.drawMidBattle(
    w: Float,
    h: Float,
    horizonY: Float,
    push: Float,
    time: Float,
    flicker: Float,
) {
    val scale = 1f + push * 0.34f
    val drift = -push * w * 0.10f
    translate(left = drift, top = horizonY * (1f - scale)) {
        scale(scale, scale, pivot = Offset(w * 0.5f, horizonY)) {
            for (i in 0 until 7) {
                val x = w * (0.10f + 0.80f * jitter(i, 21))
                val height = h * (0.115f + 0.055f * jitter(i, 22))
                val facing = if (jitter(i, 23) > 0.5f) 1f else -1f
                val bob = sin(time * 6.283f * 2f + i * 1.7f) * height * 0.012f
                drawRobot(
                    x = x,
                    footY = horizonY + bob,
                    height = height,
                    body = Color(0xFF1D2436),
                    trim = Scene.brandGlow.copy(alpha = 0.45f),
                    optic = Scene.optic.copy(alpha = 0.95f),
                    lean = facing * 0.10f,
                )
            }
            // Muzzle flashes: short, hot, and offset from the robots so they
            // read as exchanges of fire rather than decorations.
            for (i in 0 until 5) {
                val phase = (time + i * 0.21f) % 1f
                if (phase > 0.22f) continue
                val x = w * (0.12f + 0.76f * jitter(i, 31))
                val y = horizonY - h * (0.06f + 0.07f * jitter(i, 32))
                val r = h * 0.010f * (1f - phase / 0.22f)
                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            Color.White.copy(alpha = 0.95f),
                            Scene.ember.copy(alpha = 0.75f),
                            Color.Transparent,
                        ),
                        center = Offset(x, y),
                        radius = r * 3.2f,
                    ),
                    radius = r * 3.2f,
                    center = Offset(x, y),
                )
            }
        }
    }
    // Haze over the mid layer pushes it back behind the foreground.
    drawRect(
        brush = Brush.verticalGradient(
            0f to Color.Transparent,
            0.55f to Scene.skyLow.copy(alpha = 0.30f * flicker),
            1f to Scene.ground.copy(alpha = 0.85f),
            startY = horizonY - h * 0.28f,
            endY = horizonY + h * 0.06f,
        ),
        topLeft = Offset(0f, horizonY - h * 0.28f),
        size = Size(w, h * 0.34f),
    )
}

/** Ember light bleeding along the ground from the fight. */
private fun DrawScope.drawGroundGlow(
    w: Float,
    h: Float,
    horizonY: Float,
    push: Float,
    flicker: Float,
) {
    val cx = w * 0.5f
    drawRect(
        brush = Brush.radialGradient(
            colors = listOf(
                Scene.ember.copy(alpha = 0.18f * flicker),
                Scene.emberDim.copy(alpha = 0.07f * flicker),
                Color.Transparent,
            ),
            center = Offset(cx, horizonY),
            radius = w * (0.75f + push * 0.1f),
        ),
        topLeft = Offset(0f, horizonY),
        size = Size(w, h - horizonY),
    )
}

/** Two near-black robot silhouettes framing the shot. */
private fun DrawScope.drawForeground(w: Float, h: Float, horizonY: Float, push: Float) {
    val scale = 1f + push * 0.55f
    val drift = -push * w * 0.16f
    translate(left = drift, top = (horizonY + h * 0.05f) * (1f - scale)) {
        scale(scale, scale, pivot = Offset(w * 0.5f, horizonY + h * 0.05f)) {
            drawRobot(
                x = w * 0.13f,
                footY = h * 1.02f,
                height = h * 0.46f,
                body = Color(0xFF04060A),
                trim = Scene.brandGlow.copy(alpha = 0.30f),
                optic = Scene.optic.copy(alpha = 0.80f),
                lean = 0.16f,
            )
            drawRobot(
                x = w * 0.88f,
                footY = h * 1.04f,
                height = h * 0.52f,
                body = Color(0xFF04060A),
                trim = Scene.ember.copy(alpha = 0.22f),
                optic = Scene.ember.copy(alpha = 0.85f),
                lean = -0.18f,
            )
        }
    }
}

/**
 * One robot, built from primitives so it stays readable at any size.
 *
 * `footY` is the ground contact point and `height` the full standing height;
 * everything else is a fraction of those, so the same function draws a distant
 * speck and a foreground giant without branching.
 */
private fun DrawScope.drawRobot(
    x: Float,
    footY: Float,
    height: Float,
    body: Color,
    trim: Color,
    optic: Color,
    lean: Float,
) {
    val headR = height * 0.085f
    val headY = footY - height + headR
    val hipY = footY - height * 0.42f
    val shoulderY = footY - height * 0.74f
    val tilt = height * 0.055f * lean

    // Legs: two tapered struts with a knee break.
    for (side in listOf(-1f, 1f)) {
        val hipX = x + side * height * 0.045f
        val kneeX = hipX + side * height * 0.030f + tilt
        val ankleX = kneeX - side * height * 0.012f
        drawLine(
            color = body,
            start = Offset(hipX, hipY),
            end = Offset(kneeX, hipY + height * 0.20f),
            strokeWidth = height * 0.052f,
            cap = androidx.compose.ui.graphics.StrokeCap.Round,
        )
        drawLine(
            color = body,
            start = Offset(kneeX, hipY + height * 0.20f),
            end = Offset(ankleX, footY - height * 0.02f),
            strokeWidth = height * 0.044f,
            cap = androidx.compose.ui.graphics.StrokeCap.Round,
        )
        drawLine(
            color = body,
            start = Offset(ankleX - side * height * 0.035f, footY),
            end = Offset(ankleX + side * height * 0.030f, footY),
            strokeWidth = height * 0.030f,
            cap = androidx.compose.ui.graphics.StrokeCap.Round,
        )
    }

    // Torso: a plate that narrows at the waist.
    val torso = Path().apply {
        moveTo(x - height * 0.105f + tilt, shoulderY)
        lineTo(x + height * 0.105f + tilt, shoulderY)
        lineTo(x + height * 0.072f, hipY + height * 0.03f)
        lineTo(x - height * 0.072f, hipY + height * 0.03f)
        close()
    }
    drawPath(torso, color = body)
    // Chest light: a thin bar, the one bright accent on an otherwise dark body.
    drawRoundRect(
        color = trim,
        topLeft = Offset(x - height * 0.055f + tilt, shoulderY + height * 0.075f),
        size = Size(height * 0.110f, height * 0.016f),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(height * 0.008f),
    )

    // Arms, held out in a fighting stance.
    for (side in listOf(-1f, 1f)) {
        val sx = x + side * height * 0.10f + tilt
        drawLine(
            color = body,
            start = Offset(sx, shoulderY + height * 0.02f),
            end = Offset(sx + side * height * 0.115f, shoulderY + height * 0.115f),
            strokeWidth = height * 0.040f,
            cap = androidx.compose.ui.graphics.StrokeCap.Round,
        )
        drawLine(
            color = body,
            start = Offset(sx + side * height * 0.115f, shoulderY + height * 0.115f),
            end = Offset(sx + side * height * 0.150f, shoulderY + height * 0.040f),
            strokeWidth = height * 0.034f,
            cap = androidx.compose.ui.graphics.StrokeCap.Round,
        )
    }

    // Head: a visor block with two lit optics.
    drawRoundRect(
        color = body,
        topLeft = Offset(x - headR + tilt, headY - headR * 0.9f),
        size = Size(headR * 2f, headR * 1.8f),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(headR * 0.45f),
    )
    for (side in listOf(-1f, 1f)) {
        drawCircle(
            color = optic,
            radius = headR * 0.20f,
            center = Offset(x + side * headR * 0.42f + tilt, headY),
        )
    }
    // Antenna, angled back like a crest.
    drawLine(
        color = body,
        start = Offset(x + tilt, headY - headR * 0.9f),
        end = Offset(x + tilt + height * 0.030f, headY - headR * 1.9f),
        strokeWidth = height * 0.012f,
        cap = androidx.compose.ui.graphics.StrokeCap.Round,
    )
}

/** Darkened corners, so the eye lands in the middle of the frame. */
private fun DrawScope.drawVignette(w: Float, h: Float) {
    drawRect(
        brush = Brush.radialGradient(
            colors = listOf(Color.Transparent, Color.Black.copy(alpha = 0.62f)),
            center = Offset(w * 0.5f, h * 0.48f),
            radius = w * 0.95f,
        ),
        topLeft = Offset.Zero,
        size = Size(w, h),
    )
}
