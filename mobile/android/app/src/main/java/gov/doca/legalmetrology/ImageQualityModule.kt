package gov.doca.legalmetrology

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.WritableMap
import java.io.File
import java.io.FileInputStream
import java.io.InputStream
import kotlin.concurrent.thread
import kotlin.math.floor
import kotlin.math.round

/**
 * ImageQualityModule
 *
 * Implements the exact OpenCV-equivalent Laplacian variance blur detection
 * on Android device:
 *  1. Grayscale conversion via Rec.601 integer fixed-point (Y = (4899*R + 9617*G + 1868*B + 8192) >> 14).
 *  2. Downscale only if width > 800 (never upscale) with exact OpenCV bilinear interpolation.
 *  3. 2D Laplacian convolution with kernel [0, 1, 0; 1, -4, 1; 0, 1, 0] and BORDER_REFLECT_101.
 *  4. Population variance calculation.
 *  5. Threshold check at exactly 150.0 (score < 150.0 -> isBlurry = true).
 *
 * Runs 100% offline on-device with zero network requests and zero cloud dependencies.
 * Preserves the original full-resolution image file intact.
 */
class ImageQualityModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    override fun getName(): String = "ImageQualityModule"

    companion object {
        const val BLUR_THRESHOLD = 150.0
        const val TARGET_WIDTH = 800
    }

    @ReactMethod
    fun computeBlurScore(imageUri: String, promise: Promise) {
        thread(start = true) {
            val startTime = System.currentTimeMillis()
            try {
                val context = reactApplicationContext
                val uri = Uri.parse(imageUri)
                var inputStream: InputStream? = null

                try {
                    inputStream = if (uri.scheme == "content") {
                        context.contentResolver.openInputStream(uri)
                    } else {
                        val path = if (uri.scheme == "file") uri.path ?: imageUri else imageUri
                        val cleanPath = if (path.startsWith("file://")) path.substring(7) else path
                        FileInputStream(File(cleanPath))
                    }

                    if (inputStream == null) {
                        promise.reject("ERR_IMAGE_NOT_FOUND", "Could not open input stream for: $imageUri")
                        return@thread
                    }

                    val bitmap = BitmapFactory.decodeStream(inputStream)
                    if (bitmap == null) {
                        promise.reject("ERR_DECODE_FAILED", "BitmapFactory failed to decode image: $imageUri")
                        return@thread
                    }

                    val origW = bitmap.width
                    val origH = bitmap.height

                    if (origW <= 0 || origH <= 0) {
                        promise.reject("ERR_INVALID_DIMENSIONS", "Image has invalid dimensions: ${origW}x${origH}")
                        return@thread
                    }

                    // Extract ARGB pixels
                    val pixels = IntArray(origW * origH)
                    bitmap.getPixels(pixels, 0, origW, 0, 0, origW, origH)

                    // Step 1: Grayscale conversion (Rec.601 integer fixed-point matching cv2.cvtColor)
                    val origGray = IntArray(origW * origH)
                    for (i in 0 until origW * origH) {
                        val color = pixels[i]
                        val r = (color shr 16) and 0xFF
                        val g = (color shr 8) and 0xFF
                        val b = color and 0xFF
                        origGray[i] = (r * 4899 + g * 9617 + b * 1868 + 8192) shr 14
                    }

                    // Step 2: Conditional downscale (only if origW > 800, never upscale)
                    val finalW: Int
                    val finalH: Int
                    val grayData: DoubleArray

                    if (origW > TARGET_WIDTH) {
                        val scale = TARGET_WIDTH.toDouble() / origW
                        finalW = TARGET_WIDTH
                        finalH = floor(origH * scale).toInt()
                        grayData = DoubleArray(finalW * finalH)

                        for (v in 0 until finalH) {
                            val srcY = (v + 0.5) * (origH.toDouble() / finalH) - 0.5
                            val y0 = floor(srcY).toInt()
                            val y1 = y0 + 1
                            val fy = srcY - y0
                            val cy0 = y0.coerceIn(0, origH - 1)
                            val cy1 = y1.coerceIn(0, origH - 1)

                            for (u in 0 until finalW) {
                                val srcX = (u + 0.5) * (origW.toDouble() / finalW) - 0.5
                                val x0 = floor(srcX).toInt()
                                val x1 = x0 + 1
                                val fx = srcX - x0
                                val cx0 = x0.coerceIn(0, origW - 1)
                                val cx1 = x1.coerceIn(0, origW - 1)

                                val p00 = origGray[cy0 * origW + cx0].toDouble()
                                val p01 = origGray[cy0 * origW + cx1].toDouble()
                                val p10 = origGray[cy1 * origW + cx0].toDouble()
                                val p11 = origGray[cy1 * origW + cx1].toDouble()

                                val interpolated = p00 * (1.0 - fx) * (1.0 - fy) +
                                                   p01 * fx * (1.0 - fy) +
                                                   p10 * (1.0 - fx) * fy +
                                                   p11 * fx * fy
                                grayData[v * finalW + u] = round(interpolated)
                            }
                        }
                    } else {
                        // Keep original dimensions when width <= 800 (never upscale)
                        finalW = origW
                        finalH = origH
                        grayData = DoubleArray(finalW * finalH)
                        for (i in 0 until origW * origH) {
                            grayData[i] = origGray[i].toDouble()
                        }
                    }

                    // Step 3: 2D Laplacian convolution with kernel [0, 1, 0; 1, -4, 1; 0, 1, 0]
                    // and BORDER_REFLECT_101 boundary handling matching cv2.Laplacian(gray, cv2.CV_64F)
                    val laplacian = DoubleArray(finalW * finalH)
                    var sum = 0.0

                    for (y in 0 until finalH) {
                        val topY = reflect101(y - 1, finalH)
                        val bottomY = reflect101(y + 1, finalH)

                        for (x in 0 until finalW) {
                            val leftX = reflect101(x - 1, finalW)
                            val rightX = reflect101(x + 1, finalW)

                            val center = grayData[y * finalW + x]
                            val top = grayData[topY * finalW + x]
                            val bottom = grayData[bottomY * finalW + x]
                            val left = grayData[y * finalW + leftX]
                            val right = grayData[y * finalW + rightX]

                            val lapVal = top + bottom + left + right - 4.0 * center
                            laplacian[y * finalW + x] = lapVal
                            sum += lapVal
                        }
                    }

                    // Step 4: Population variance calculation
                    val totalPixels = finalW * finalH
                    val mean = sum / totalPixels
                    var varianceSum = 0.0
                    for (i in 0 until totalPixels) {
                        val diff = laplacian[i] - mean
                        varianceSum += diff * diff
                    }
                    val sharpnessScore = varianceSum / totalPixels

                    // Step 5: Decision with exact threshold 150.0
                    val isBlurry = sharpnessScore < BLUR_THRESHOLD

                    val executionTimeMs = (System.currentTimeMillis() - startTime).toDouble()
                    val result: WritableMap = Arguments.createMap().apply {
                        putBoolean("isBlurry", isBlurry)
                        putDouble("sharpnessScore", sharpnessScore)
                        putDouble("threshold", BLUR_THRESHOLD)
                        putInt("width", origW)
                        putInt("height", origH)
                        putDouble("executionTimeMs", executionTimeMs)
                    }

                    promise.resolve(result)
                } finally {
                    inputStream?.close()
                }
            } catch (e: Exception) {
                promise.reject("ERR_QUALITY_CHECK", "Blur computation error: ${e.message}", e)
            }
        }
    }

    /**
     * Reflect-101 border index helper:
     * Reflects without duplicating the edge element:
     * e.g. for length 4 (indices 0, 1, 2, 3):
     *  index -1 -> 1
     *  index  4 -> 2
     */
    private fun reflect101(index: Int, size: Int): Int {
        if (size <= 1) return 0
        return when {
            index < 0 -> -index
            index >= size -> 2 * (size - 1) - index
            else -> index
        }.coerceIn(0, size - 1)
    }
}
