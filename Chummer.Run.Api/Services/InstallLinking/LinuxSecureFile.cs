using Microsoft.Win32.SafeHandles;
using System.Runtime.InteropServices;

namespace Chummer.Run.Api.Services.InstallLinking;

internal static class LinuxSecureFile
{
    private const int OpenReadOnly = 0;
    private const int OpenReadWrite = 2;
    private const int OpenCreate = 0x40;
    private const int OpenCloseOnExec = 0x80000;
    private const int OpenNoFollow = 0x20000;
    private const int OpenDirectory = 0x10000;
    private const int LockExclusive = 2;
    private const int LockNonBlocking = 4;
    private const uint FileTypeMask = 0xF000;
    private const uint RegularFile = 0x8000;
    private const uint DirectoryFile = 0x4000;
    private const uint OwnerReadWriteMode = 0x180;

    public static bool IsSupportedPlatform
        => OperatingSystem.IsLinux()
            && RuntimeInformation.ProcessArchitecture == Architecture.X64;

    public static byte[] ReadOwnerOnlyRegularFile(string path, int maximumBytes, bool repairOwnerMode)
    {
        if (!IsSupportedPlatform)
        {
            throw new PlatformNotSupportedException("Secure no-follow file reads require Linux.");
        }

        int descriptor = NativeOpen(path, OpenReadOnly | OpenCloseOnExec | OpenNoFollow);
        if (descriptor < 0)
        {
            throw new IOException("Secure file could not be opened.");
        }

        using var handle = new SafeFileHandle((IntPtr)descriptor, ownsHandle: true);
        LinuxStat metadata = ValidateDescriptor(descriptor, maximumBytes);
        if (repairOwnerMode)
        {
            if (NativeFchmod(descriptor, OwnerReadWriteMode) != 0)
            {
                throw new IOException("Secure file permissions could not be restricted.");
            }
        }
        else if ((metadata.Mode & 0x3F) != 0 || (metadata.Mode & 0x100) == 0)
        {
            throw new UnauthorizedAccessException("Secure file permissions are invalid.");
        }

        byte[] bytes = GC.AllocateUninitializedArray<byte>(checked((int)metadata.Size));
        using var stream = new FileStream(handle, FileAccess.Read, bufferSize: 64 * 1024, isAsync: false);
        stream.ReadExactly(bytes);
        return bytes;
    }

    public static FileStream AcquireOwnerOnlyWriterLease(string path)
    {
        if (!IsSupportedPlatform)
        {
            throw new PlatformNotSupportedException("Install-linking single-writer locking requires Linux.");
        }

        int descriptor = NativeOpenWithMode(
            path,
            OpenReadWrite | OpenCreate | OpenCloseOnExec | OpenNoFollow,
            OwnerReadWriteMode);
        if (descriptor < 0)
        {
            throw new IOException("Install-linking writer lease could not be opened.");
        }

        var handle = new SafeFileHandle((IntPtr)descriptor, ownsHandle: true);
        try
        {
            _ = ValidateDescriptor(descriptor, maximumBytes: 4096);
            if (NativeFchmod(descriptor, OwnerReadWriteMode) != 0
                || NativeFlock(descriptor, LockExclusive | LockNonBlocking) != 0)
            {
                throw new IOException("Install-linking writer lease is already held.");
            }

            return new FileStream(handle, FileAccess.ReadWrite, bufferSize: 1, isAsync: false);
        }
        catch
        {
            handle.Dispose();
            throw;
        }
    }

    public static void PrepareOwnerOnlyDirectory(string path)
    {
        if (!IsSupportedPlatform)
        {
            throw new PlatformNotSupportedException("Secure directory validation requires Linux.");
        }

        Directory.CreateDirectory(path);
        DirectoryInfo? current = new(path);
        while (current is not null)
        {
            current.Refresh();
            if ((current.Attributes & FileAttributes.ReparsePoint) != 0 || current.LinkTarget is not null)
            {
                throw new InvalidOperationException("Secure directory path cannot contain links.");
            }

            current = current.Parent;
        }

        int descriptor = NativeOpen(path, OpenReadOnly | OpenDirectory | OpenCloseOnExec | OpenNoFollow);
        if (descriptor < 0)
        {
            throw new IOException("Secure directory could not be opened.");
        }

        using var handle = new SafeFileHandle((IntPtr)descriptor, ownsHandle: true);
        if (NativeFstat(descriptor, out LinuxStat metadata) != 0
            || (metadata.Mode & FileTypeMask) != DirectoryFile
            || metadata.UserId != NativeGetEffectiveUserId()
            || NativeFchmod(descriptor, 0x1C0) != 0)
        {
            throw new UnauthorizedAccessException("Secure directory metadata is invalid.");
        }
    }

    private static LinuxStat ValidateDescriptor(int descriptor, int maximumBytes)
    {
        if (NativeFstat(descriptor, out LinuxStat metadata) != 0
            || (metadata.Mode & FileTypeMask) != RegularFile
            || metadata.LinkCount != 1
            || metadata.UserId != NativeGetEffectiveUserId()
            || metadata.Size is < 0
            || metadata.Size > maximumBytes)
        {
            throw new InvalidDataException("Secure file metadata is invalid.");
        }

        return metadata;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LinuxStat
    {
        public ulong Device;
        public ulong Inode;
        public ulong LinkCount;
        public uint Mode;
        public uint UserId;
        public uint GroupId;
        public int Padding;
        public ulong SpecialDevice;
        public long Size;
        public long BlockSize;
        public long Blocks;
        public long AccessSeconds;
        public long AccessNanoseconds;
        public long ModifiedSeconds;
        public long ModifiedNanoseconds;
        public long ChangedSeconds;
        public long ChangedNanoseconds;
        public long Reserved0;
        public long Reserved1;
        public long Reserved2;
    }

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int NativeOpen(string path, int flags);

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int NativeOpenWithMode(string path, int flags, uint mode);

    [DllImport("libc", EntryPoint = "fstat", SetLastError = true)]
    private static extern int NativeFstat(int descriptor, out LinuxStat metadata);

    [DllImport("libc", EntryPoint = "fchmod", SetLastError = true)]
    private static extern int NativeFchmod(int descriptor, uint mode);

    [DllImport("libc", EntryPoint = "flock", SetLastError = true)]
    private static extern int NativeFlock(int descriptor, int operation);

    [DllImport("libc", EntryPoint = "geteuid")]
    private static extern uint NativeGetEffectiveUserId();
}
