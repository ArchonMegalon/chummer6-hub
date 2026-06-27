using System.Reflection;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingContactUploadTests
{
    [Fact]
    public void SubmitContactCasePinsMultipartBodyLimitsToAttachmentBudget()
    {
        MethodInfo method = typeof(PublicLandingController).GetMethod(nameof(PublicLandingController.SubmitContactCase))
            ?? throw new InvalidOperationException("PublicLandingController.SubmitContactCase was not found.");

        RequestSizeLimitAttribute requestSize = method.GetCustomAttribute<RequestSizeLimitAttribute>()
            ?? throw new InvalidOperationException("SubmitContactCase is missing RequestSizeLimitAttribute.");
        RequestFormLimitsAttribute formLimits = method.GetCustomAttribute<RequestFormLimitsAttribute>()
            ?? throw new InvalidOperationException("SubmitContactCase is missing RequestFormLimitsAttribute.");

        Assert.Equal(SupportAttachmentStorageService.MaxMultipartBodyBytes, ((IRequestSizeLimitMetadata)requestSize).MaxRequestBodySize);
        Assert.Equal(SupportAttachmentStorageService.MaxMultipartBodyBytes, formLimits.MultipartBodyLengthLimit);
    }

    [Fact]
    public async Task ReadSupportUploadsRejectsTooManyFilesBeforeBuffering()
    {
        List<IFormFile> files = Enumerable.Range(0, SupportAttachmentStorageService.MaxAttachmentCount + 1)
            .Select(index => CreateFormFile($"case-{index}.log", 32))
            .Cast<IFormFile>()
            .ToList();

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() => InvokeReadSupportUploadsAsync(files));

        Assert.Contains("up to five attachments", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ReadSupportUploadsRejectsOversizedFileBeforeBuffering()
    {
        IFormFile file = CreateFormFile("case.log", SupportAttachmentStorageService.MaxAttachmentBytes + 1L);

        InvalidDataException ex = await Assert.ThrowsAsync<InvalidDataException>(() => InvokeReadSupportUploadsAsync([file]));

        Assert.Contains("8 MB limit", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ReadSupportUploadsPreservesSmallValidFiles()
    {
        IFormFile file = CreateFormFile("case.log", 128);

        IReadOnlyList<SupportAttachmentUpload> uploads = await InvokeReadSupportUploadsAsync([file]);

        SupportAttachmentUpload upload = Assert.Single(uploads);
        Assert.Equal("case.log", upload.FileName);
        Assert.Equal(128, upload.Content.Length);
    }

    private static async Task<IReadOnlyList<SupportAttachmentUpload>> InvokeReadSupportUploadsAsync(IReadOnlyList<IFormFile>? files)
    {
        MethodInfo method = typeof(PublicLandingController).GetMethod("ReadSupportUploadsAsync", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("PublicLandingController.ReadSupportUploadsAsync was not found.");

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
