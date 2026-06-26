using System.Reflection;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc;
using Xunit;

namespace Chummer.Tests;

public sealed class SupportCasesControllerUploadTests
{
    [Fact]
    public void SubmitFromFormPinsMultipartBodyLimitsToAttachmentBudget()
    {
        MethodInfo method = typeof(SupportCasesController).GetMethod(nameof(SupportCasesController.SubmitFromForm))
            ?? throw new InvalidOperationException("SupportCasesController.SubmitFromForm was not found.");

        RequestSizeLimitAttribute requestSize = method.GetCustomAttribute<RequestSizeLimitAttribute>()
            ?? throw new InvalidOperationException("SubmitFromForm is missing RequestSizeLimitAttribute.");
        RequestFormLimitsAttribute formLimits = method.GetCustomAttribute<RequestFormLimitsAttribute>()
            ?? throw new InvalidOperationException("SubmitFromForm is missing RequestFormLimitsAttribute.");

        Assert.Equal(SupportAttachmentStorageService.MaxMultipartBodyBytes, ((IRequestSizeLimitMetadata)requestSize).MaxRequestBodySize);
        Assert.Equal(SupportAttachmentStorageService.MaxMultipartBodyBytes, formLimits.MultipartBodyLengthLimit);
    }

    [Fact]
    public async Task ReadUploadsRejectsTooManyFilesBeforeBuffering()
    {
        List<IFormFile> files = Enumerable.Range(0, SupportAttachmentStorageService.MaxAttachmentCount + 1)
            .Select(index => CreateFormFile($"case-{index}.log", 32))
            .Cast<IFormFile>()
            .ToList();

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() => InvokeReadUploadsAsync(files));

        Assert.Contains("up to five attachments", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ReadUploadsRejectsOversizedFileBeforeBuffering()
    {
        IFormFile file = CreateFormFile("case.log", SupportAttachmentStorageService.MaxAttachmentBytes + 1L);

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() => InvokeReadUploadsAsync([file]));

        Assert.Contains("8 MB limit", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ReadUploadsPreservesSmallValidFiles()
    {
        IFormFile file = CreateFormFile("case.log", 128);

        IReadOnlyList<SupportAttachmentUpload> uploads = await InvokeReadUploadsAsync([file]);

        SupportAttachmentUpload upload = Assert.Single(uploads);
        Assert.Equal("case.log", upload.FileName);
        Assert.Equal(128, upload.Content.Length);
    }

    private static async Task<IReadOnlyList<SupportAttachmentUpload>> InvokeReadUploadsAsync(IReadOnlyList<IFormFile>? files)
    {
        MethodInfo method = typeof(SupportCasesController).GetMethod("ReadUploadsAsync", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("SupportCasesController.ReadUploadsAsync was not found.");

        object? result = method.Invoke(null, [files, CancellationToken.None]);
        Task<IReadOnlyList<SupportAttachmentUpload>> task = Assert.IsAssignableFrom<Task<IReadOnlyList<SupportAttachmentUpload>>>(result);
        return await task;
    }

    private static FormFile CreateFormFile(string fileName, long length)
    {
        var buffer = new byte[checked((int)length)];
        return new FormFile(new MemoryStream(buffer), 0, length, "attachments", fileName)
        {
            Headers = new HeaderDictionary(),
            ContentType = "text/plain"
        };
    }
}
