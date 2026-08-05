import AVFoundation
@preconcurrency import CoreML
import Darwin
import Foundation
@preconcurrency import WhisperKit

// The one Argmax revision this worker is allowed to build against.  The Python
// driver checks the local checkout against this value before every build and
// folds it into the worker cache fingerprint, so a moved or dirty checkout can
// never silently change decoding behaviour.
private let requiredArgmaxRevision = "dcf3a00f0ae4d5b57bc0aad92063b102b70d5fd1"

// Fixed M5 configuration, identical to the settings the established WhisperKit
// baseline was produced with.
private let modelName = "large-v3-v20240930_turbo"
private let chunkingStrategyName = "vad"
private let concurrentWorkerCount = 64

private struct Request: Decodable {
    let id: String
    let type: String
    let audioPath: String?
    let language: String?
    let timestamps: Bool?

    private enum CodingKeys: String, CodingKey {
        case id
        case type
        case audioPath = "audio_path"
        case language
        case timestamps
    }
}

private struct ProtocolSegment: Encodable {
    let start: Double
    let end: Double
    let text: String
}

private struct ProtocolWriter {
    let handle: FileHandle
    let encoder = JSONEncoder()

    func emit<T: Encodable>(_ frame: T) throws {
        var payload = try encoder.encode(frame)
        payload.append(0x0A)
        try handle.write(contentsOf: payload)
    }
}

private struct ReadyFrame: Encodable {
    let type = "ready"
    let engine = "whisperkit"
    let model: String
    let modelPath: String
    let audioEncoderComputeUnits: String
    let textDecoderComputeUnits: String
    let concurrentWorkerCount: Int
    let chunkingStrategy: String
    let argmaxRevision: String
    let workerVersion: String
    let modelLoadSeconds: Double

    private enum CodingKeys: String, CodingKey {
        case type
        case engine
        case model
        case modelPath = "model_path"
        case audioEncoderComputeUnits = "audio_encoder_compute_units"
        case textDecoderComputeUnits = "text_decoder_compute_units"
        case concurrentWorkerCount = "concurrent_worker_count"
        case chunkingStrategy = "chunking_strategy"
        case argmaxRevision = "argmax_revision"
        case workerVersion = "worker_version"
        case modelLoadSeconds = "model_load_seconds"
    }
}

private struct ResultFrame: Encodable {
    let id: String
    let type = "result"
    let text: String
    let segments: [ProtocolSegment]
    let duration: Double
    let processingTime: Double
    let language: String?
    let model: String
    let modelPath: String
    let argmaxRevision: String

    private enum CodingKeys: String, CodingKey {
        case id
        case type
        case text
        case segments
        case duration
        case processingTime = "processing_time"
        case language
        case model
        case modelPath = "model_path"
        case argmaxRevision = "argmax_revision"
    }
}

private struct ErrorFrame: Encodable {
    let id: String?
    let type = "error"
    let code: String
    let message: String
    let retriable: Bool
}

private struct StatusFrame: Encodable {
    let type: String
    let ready: Bool
    let engine = "whisperkit"
    let model: String
    let modelPath: String
    let audioEncoderComputeUnits: String
    let textDecoderComputeUnits: String
    let argmaxRevision: String
    let workerVersion: String

    private enum CodingKeys: String, CodingKey {
        case type
        case ready
        case engine
        case model
        case modelPath = "model_path"
        case audioEncoderComputeUnits = "audio_encoder_compute_units"
        case textDecoderComputeUnits = "text_decoder_compute_units"
        case argmaxRevision = "argmax_revision"
        case workerVersion = "worker_version"
    }
}

private func computeUnits(
    from variable: String,
    default fallback: MLComputeUnits,
    defaultName: String
) -> (MLComputeUnits, String) {
    switch ProcessInfo.processInfo.environment[variable] {
    case "cpuOnly":
        return (.cpuOnly, "cpuOnly")
    case "cpuAndGPU":
        return (.cpuAndGPU, "cpuAndGPU")
    case "cpuAndNeuralEngine":
        return (.cpuAndNeuralEngine, "cpuAndNeuralEngine")
    case "all":
        return (.all, "all")
    default:
        return (fallback, defaultName)
    }
}

private func selectedComputeUnits() -> (
    encoder: MLComputeUnits,
    encoderName: String,
    decoder: MLComputeUnits,
    decoderName: String
) {
    let (encoder, encoderName) = computeUnits(
        from: "WHISPERKIT_AUDIO_ENCODER_COMPUTE_UNITS",
        default: .cpuAndNeuralEngine,
        defaultName: "cpuAndNeuralEngine"
    )
    let (decoder, decoderName) = computeUnits(
        from: "WHISPERKIT_TEXT_DECODER_COMPUTE_UNITS",
        default: .cpuAndGPU,
        defaultName: "cpuAndGPU"
    )
    return (encoder, encoderName, decoder, decoderName)
}

private func currentWorkerVersion() -> String {
    Bundle.main.executableURL?
        .deletingLastPathComponent()
        .lastPathComponent ?? "unknown"
}

private func resolvedModelPath() -> String? {
    ProcessInfo.processInfo.environment["WHISPERKIT_WORKER_MODEL_PATH"]
}

private func requiredBundlesPresent(at path: String) -> Bool {
    let root = URL(fileURLWithPath: path)
    for bundle in ["AudioEncoder.mlmodelc", "TextDecoder.mlmodelc"] {
        if !FileManager.default.fileExists(atPath: root.appendingPathComponent(bundle).path) {
            return false
        }
    }
    return true
}

private func audioDuration(_ url: URL) throws -> Double {
    let file = try AVAudioFile(forReading: url)
    let sampleRate = file.processingFormat.sampleRate
    guard sampleRate.isFinite, sampleRate > 0 else {
        throw WhisperError.loadAudioFailed("audio file reports no usable sample rate")
    }
    return Double(file.length) / sampleRate
}

private func protocolError(id: String?, error: Error) -> ErrorFrame {
    let message = error.localizedDescription
    guard let whisperError = error as? WhisperError else {
        if let cocoa = error as? CocoaError, cocoa.isFileError {
            return ErrorFrame(
                id: id,
                code: "file_access_failed",
                message: message,
                retriable: false
            )
        }
        return ErrorFrame(
            id: id,
            code: "internal_error",
            message: message,
            retriable: false
        )
    }
    switch whisperError {
    case .loadAudioFailed, .audioProcessingFailed:
        return ErrorFrame(id: id, code: "invalid_audio", message: message, retriable: false)
    case .modelsUnavailable, .tokenizerUnavailable, .initializationError:
        return ErrorFrame(id: id, code: "model_load_failed", message: message, retriable: true)
    case .decodingLogitsFailed,
         .segmentingFailed,
         .prepareDecoderInputsFailed,
         .transcriptionFailed,
         .decodingFailed:
        return ErrorFrame(id: id, code: "processing_failed", message: message, retriable: true)
    case .microphoneUnavailable:
        return ErrorFrame(id: id, code: "internal_error", message: message, retriable: false)
    }
}

/// Build the decoding options `whisperkit-cli transcribe` would build for the
/// established baseline invocation.
///
/// `firstTokenLogProbThreshold` is deliberately `nil`: the CLI forwards its own
/// unset `Float?` argument rather than the `DecodingOptions` default of -1.5, and
/// matching the CLI here is what keeps transcripts comparable.
private func decodingOptions(language: String?, timestamps: Bool) -> DecodingOptions {
    DecodingOptions(
        verbose: false,
        task: .transcribe,
        language: language,
        temperature: 0,
        temperatureIncrementOnFallback: 0.2,
        temperatureFallbackCount: 5,
        topK: 5,
        usePrefillPrompt: language != nil,
        skipSpecialTokens: true,
        withoutTimestamps: !timestamps,
        wordTimestamps: false,
        clipTimestamps: [],
        suppressTokens: [],
        compressionRatioThreshold: 2.4,
        logProbThreshold: -1.0,
        firstTokenLogProbThreshold: nil,
        noSpeechThreshold: 0.6,
        concurrentWorkerCount: concurrentWorkerCount,
        chunkingStrategy: .vad
    )
}

private func loadWhisperKit(
    modelPath: String,
    encoder: MLComputeUnits,
    decoder: MLComputeUnits
) async throws -> WhisperKit {
    let config = WhisperKitConfig(
        model: modelName,
        modelFolder: modelPath,
        computeOptions: ModelComputeOptions(
            audioEncoderCompute: encoder,
            textDecoderCompute: decoder
        ),
        verbose: false,
        logLevel: .info,
        prewarm: false,
        load: true,
        download: false,
        useBackgroundDownloadSession: false
    )
    return try await WhisperKit(config)
}

private func transcribeOnce(
    whisperKit: WhisperKit,
    audioPath: String,
    language: String?,
    timestamps: Bool
) async throws -> TranscriptionResult {
    let options = decodingOptions(language: language, timestamps: timestamps)
    let results = await whisperKit.transcribeWithResults(
        audioPaths: [audioPath],
        decodeOptions: options
    )
    guard let first = results.first else {
        throw WhisperError.transcriptionFailed("worker received no transcription result")
    }
    let partial = try first.get()
    return TranscriptionUtilities.mergeTranscriptionResults(partial)
}

private func resultFrame(
    id: String,
    modelPath: String,
    result: TranscriptionResult,
    duration: Double,
    processingTime: Double
) -> ResultFrame {
    let segments = result.segments.map {
        ProtocolSegment(
            start: Double($0.start),
            end: Double($0.end),
            text: $0.text
        )
    }
    return ResultFrame(
        id: id,
        text: result.text,
        segments: segments,
        duration: duration,
        processingTime: processingTime,
        language: result.language,
        model: modelName,
        modelPath: modelPath,
        argmaxRevision: requiredArgmaxRevision
    )
}

private func serveSelfTest(writer: ProtocolWriter, encoderName: String, decoderName: String) throws {
    let modelPath = resolvedModelPath() ?? "/selftest/openai_whisper-\(modelName)"
    try writer.emit(
        ReadyFrame(
            model: modelName,
            modelPath: modelPath,
            audioEncoderComputeUnits: encoderName,
            textDecoderComputeUnits: decoderName,
            concurrentWorkerCount: concurrentWorkerCount,
            chunkingStrategy: chunkingStrategyName,
            argmaxRevision: requiredArgmaxRevision,
            workerVersion: currentWorkerVersion(),
            modelLoadSeconds: 0
        )
    )
    while let line = readLine(strippingNewline: true) {
        guard let data = line.data(using: .utf8) else { continue }
        do {
            let request = try JSONDecoder().decode(Request.self, from: data)
            if request.type == "shutdown" {
                return
            }
            guard request.type == "transcribe" else {
                try writer.emit(
                    ErrorFrame(
                        id: request.id,
                        code: "internal_error",
                        message: "unsupported request type",
                        retriable: false
                    )
                )
                continue
            }
            try writer.emit(
                ResultFrame(
                    id: request.id,
                    text: "Hello world.",
                    segments: [
                        ProtocolSegment(start: 0.0, end: 0.8, text: " Hello world.")
                    ],
                    duration: 1.0,
                    processingTime: 0.01,
                    language: request.language ?? "en",
                    model: modelName,
                    modelPath: modelPath,
                    argmaxRevision: requiredArgmaxRevision
                )
            )
        } catch {
            try writer.emit(protocolError(id: nil, error: error))
        }
    }
}

private func serve(
    writer: ProtocolWriter,
    modelPath: String,
    encoder: MLComputeUnits,
    encoderName: String,
    decoder: MLComputeUnits,
    decoderName: String
) async throws {
    let loadStarted = Date()
    let whisperKit = try await loadWhisperKit(
        modelPath: modelPath,
        encoder: encoder,
        decoder: decoder
    )
    let modelLoadSeconds = Date().timeIntervalSince(loadStarted)
    try writer.emit(
        ReadyFrame(
            model: modelName,
            modelPath: modelPath,
            audioEncoderComputeUnits: encoderName,
            textDecoderComputeUnits: decoderName,
            concurrentWorkerCount: concurrentWorkerCount,
            chunkingStrategy: chunkingStrategyName,
            argmaxRevision: requiredArgmaxRevision,
            workerVersion: currentWorkerVersion(),
            modelLoadSeconds: modelLoadSeconds
        )
    )

    while let line = readLine(strippingNewline: true) {
        guard let data = line.data(using: .utf8) else { continue }
        let request: Request
        do {
            request = try JSONDecoder().decode(Request.self, from: data)
        } catch {
            try writer.emit(protocolError(id: nil, error: error))
            continue
        }
        if request.type == "shutdown" {
            return
        }
        guard request.type == "transcribe", let audioPath = request.audioPath else {
            try writer.emit(
                ErrorFrame(
                    id: request.id,
                    code: "internal_error",
                    message: "transcribe requires audio_path",
                    retriable: false
                )
            )
            continue
        }

        do {
            let url = URL(fileURLWithPath: audioPath)
            let duration: Double
            do {
                duration = try audioDuration(url)
            } catch {
                try writer.emit(
                    ErrorFrame(
                        id: request.id,
                        code: "file_access_failed",
                        message: error.localizedDescription,
                        retriable: false
                    )
                )
                continue
            }
            let started = Date()
            let result = try await transcribeOnce(
                whisperKit: whisperKit,
                audioPath: audioPath,
                language: request.language,
                timestamps: request.timestamps ?? false
            )
            try writer.emit(
                resultFrame(
                    id: request.id,
                    modelPath: modelPath,
                    result: result,
                    duration: duration,
                    processingTime: Date().timeIntervalSince(started)
                )
            )
        } catch {
            try writer.emit(protocolError(id: request.id, error: error))
        }
    }
}

@main
private struct WhisperKitWorkerMain {
    static func main() async {
        let protocolFD = dup(STDOUT_FILENO)
        guard protocolFD >= 0 else {
            fputs("could not duplicate protocol descriptor\n", stderr)
            Darwin.exit(2)
        }
        guard dup2(STDERR_FILENO, STDOUT_FILENO) >= 0 else {
            fputs("could not isolate protocol descriptor\n", stderr)
            Darwin.close(protocolFD)
            Darwin.exit(2)
        }
        let writer = ProtocolWriter(handle: FileHandle(fileDescriptor: protocolFD, closeOnDealloc: true))
        let units = selectedComputeUnits()
        let arguments = Set(CommandLine.arguments.dropFirst())

        do {
            if arguments.contains("--selftest") {
                print("whisperkit selftest diagnostic")
                try serveSelfTest(
                    writer: writer,
                    encoderName: units.encoderName,
                    decoderName: units.decoderName
                )
                return
            }
            guard let modelPath = resolvedModelPath() else {
                try writer.emit(
                    ErrorFrame(
                        id: nil,
                        code: "model_load_failed",
                        message: "WHISPERKIT_WORKER_MODEL_PATH is not set",
                        retriable: false
                    )
                )
                Darwin.exit(2)
            }
            if arguments.contains("--check") {
                let ready = requiredBundlesPresent(at: modelPath)
                try writer.emit(
                    StatusFrame(
                        type: "check",
                        ready: ready,
                        model: modelName,
                        modelPath: modelPath,
                        audioEncoderComputeUnits: units.encoderName,
                        textDecoderComputeUnits: units.decoderName,
                        argmaxRevision: requiredArgmaxRevision,
                        workerVersion: currentWorkerVersion()
                    )
                )
                Darwin.exit(ready ? 0 : 3)
            }
            try await serve(
                writer: writer,
                modelPath: modelPath,
                encoder: units.encoder,
                encoderName: units.encoderName,
                decoder: units.decoder,
                decoderName: units.decoderName
            )
        } catch {
            try? writer.emit(protocolError(id: nil, error: error))
            fputs("whisperkit-worker: \(error.localizedDescription)\n", stderr)
            Darwin.exit(2)
        }
    }
}
