using System;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using Whisper.net;
// WhisperService — stdin/stdout IPC сервис для транскрипции аудио.
//
// Протокол (бинарный, little-endian):
//   Python -> C#:
//     4 байта (int32): длина WAV-данных в байтах
//     N байт:          WAV-данные (mono, 16kHz, 16-bit PCM)
//
//   C# -> Python:
//     4 байта (int32): длина текста в байтах (UTF-8), либо -1 при ошибке
//     N байт:          текст (UTF-8)
//
// length == 0 от Python => команда завершения сервиса.

class Program
{
    static async Task<int> Main(string[] args)
    {
        if (args.Length < 1)
        {
            Console.Error.WriteLine("Usage: WhisperService <model_path> [language]");
            return 1;
        }

        string modelPath = args[0];
        string language = args.Length > 1 ? args[1] : "ru";

        if (!File.Exists(modelPath))
        {
            Console.Error.WriteLine($"Model file not found: {modelPath}");
            return 1;
        }

        Console.Error.WriteLine($"[WhisperService] Loading model: {modelPath}");
        Console.Error.WriteLine($"[WhisperService] Language: {language}");

        WhisperFactory? factory = null;
        WhisperProcessor? processor = null;

        try
        {
            factory = WhisperFactory.FromPath(modelPath);

            var builder = factory.CreateBuilder().WithNoContext();
            // Empty string or "auto" = auto-detect language
            if (!string.IsNullOrEmpty(language) && language != "auto")
                builder = builder.WithLanguage(language);
            processor = builder.Build();

            Console.Error.WriteLine("[WhisperService] Ready");

            using var stdin = new BinaryReader(Console.OpenStandardInput(), Encoding.UTF8, leaveOpen: true);
            using var stdout = new BinaryWriter(Console.OpenStandardOutput(), Encoding.UTF8, leaveOpen: true);

            while (true)
            {
                int length;
                try
                {
                    length = stdin.ReadInt32();
                }
                catch (EndOfStreamException)
                {
                    break;
                }

                if (length == 0)
                    break;

                if (length < 0 || length > 100 * 1024 * 1024)
                {
                    Console.Error.WriteLine($"[WhisperService] Invalid chunk size: {length}");
                    WriteError(stdout, "Invalid chunk size");
                    continue;
                }

                byte[] wavData = stdin.ReadBytes(length);
                if (wavData.Length != length)
                {
                    WriteError(stdout, "Incomplete WAV data");
                    continue;
                }

                try
                {
                    string text = await TranscribeAsync(processor, wavData);
                    WriteResponse(stdout, text);
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"[WhisperService] Transcription error: {ex.Message}");
                    WriteError(stdout, ex.Message);
                }
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[WhisperService] Fatal: {ex}");
            return 2;
        }
        finally
        {
            processor?.Dispose();
            factory?.Dispose();
            Console.Error.WriteLine("[WhisperService] Shutdown");
        }

        return 0;
    }

    static async Task<string> TranscribeAsync(WhisperProcessor processor, byte[] wavData)
    {
        using var stream = new MemoryStream(wavData);
        var sb = new StringBuilder();

        await foreach (var segment in processor.ProcessAsync(stream))
        {
            if (segment.Text is { Length: > 0 })
                sb.Append(segment.Text);
        }

        return sb.ToString().Trim();
    }

    static void WriteResponse(BinaryWriter writer, string text)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(text);
        writer.Write(bytes.Length);
        writer.Write(bytes);
        writer.Flush();
    }

    static void WriteError(BinaryWriter writer, string message)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(message);
        // -1 сигнализирует об ошибке, затем длина + текст ошибки
        writer.Write(-1);
        writer.Write(bytes.Length);
        writer.Write(bytes);
        writer.Flush();
    }
}
