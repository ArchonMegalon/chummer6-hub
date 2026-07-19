using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Linux descriptor-relative reader for the immutable public projection tree.
/// Every ancestor is opened with O_NOFOLLOW, files must be single-link regular
/// files, and pathname identities are rechecked around each bounded read.
/// </summary>
internal sealed class PublicProjectionDescriptorReader : IDisposable
{
    private readonly string _rootPath;
    private readonly int _rootDescriptor;
    private readonly LinuxStatx _rootIdentity;
    private bool _disposed;

    private PublicProjectionDescriptorReader(
        string rootPath,
        int rootDescriptor,
        LinuxStatx rootIdentity)
    {
        _rootPath = rootPath;
        _rootDescriptor = rootDescriptor;
        _rootIdentity = rootIdentity;
    }

    public static PublicProjectionDescriptorReader Open(string rootPath)
    {
        if (!OperatingSystem.IsLinux())
        {
            throw new PlatformNotSupportedException(
                "authenticated public projection descriptor reads require Linux");
        }

        string normalized = Path.TrimEndingDirectorySeparator(Path.GetFullPath(rootPath));
        int descriptor = OpenAbsoluteDirectory(normalized, "public projection snapshot root");
        try
        {
            LinuxStatx identity = StatDescriptor(descriptor, "public projection snapshot root");
            RequireDirectory(identity, "public projection snapshot root");
            return new PublicProjectionDescriptorReader(normalized, descriptor, identity);
        }
        catch
        {
            NativeClose(descriptor);
            throw;
        }
    }

    public byte[] ReadRootFile(string name, int maximumBytes, string label)
        => ReadRegularFile(_rootDescriptor, name, maximumBytes, label);

    public PublicProjectionDescriptorDirectory OpenDirectory(string name, string label)
    {
        ValidateSingleComponent(name, label);
        int descriptor = LinuxNative.openat(
            _rootDescriptor,
            name,
            LinuxNative.OpenReadOnly
            | LinuxNative.OpenCloseOnExec
            | LinuxNative.OpenNoFollow
            | LinuxNative.OpenDirectory);
        if (descriptor < 0)
        {
            throw new InvalidDataException($"{label} has unsafe directory identity");
        }

        try
        {
            LinuxStatx identity = StatDescriptor(descriptor, label);
            RequireDirectory(identity, label);
            VerifyDirectoryEntry(_rootDescriptor, name, identity, label);
            return new PublicProjectionDescriptorDirectory(
                _rootDescriptor,
                descriptor,
                name,
                label,
                identity);
        }
        catch
        {
            NativeClose(descriptor);
            throw;
        }
    }

    public void VerifyRootPathIdentity()
    {
        int currentDescriptor = OpenAbsoluteDirectory(
            _rootPath,
            "public projection snapshot root");
        try
        {
            LinuxStatx currentIdentity = StatDescriptor(
                currentDescriptor,
                "public projection snapshot root");
            if (!SameDirectoryIdentity(_rootIdentity, currentIdentity))
            {
                throw new InvalidDataException(
                    "public projection snapshot root changed during authentication");
            }
        }
        finally
        {
            NativeClose(currentDescriptor);
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }
        _disposed = true;
        NativeClose(_rootDescriptor);
    }

    internal sealed class PublicProjectionDescriptorDirectory : IDisposable
    {
        private readonly int _parentDescriptor;
        private readonly int _descriptor;
        private readonly string _entryName;
        private readonly string _label;
        private readonly LinuxStatx _identity;
        private bool _disposed;

        internal PublicProjectionDescriptorDirectory(
            int parentDescriptor,
            int descriptor,
            string entryName,
            string label,
            LinuxStatx identity)
        {
            _parentDescriptor = parentDescriptor;
            _descriptor = descriptor;
            _entryName = entryName;
            _label = label;
            _identity = identity;
        }

        public byte[] ReadFile(string name, int maximumBytes, string label)
            => ReadRegularFile(_descriptor, name, maximumBytes, label);

        public void VerifyPathIdentity()
            => VerifyDirectoryEntry(
                _parentDescriptor,
                _entryName,
                _identity,
                _label);

        public void Dispose()
        {
            if (_disposed)
            {
                return;
            }
            _disposed = true;
            NativeClose(_descriptor);
        }
    }

    private static int OpenAbsoluteDirectory(string absolutePath, string label)
    {
        if (!Path.IsPathFullyQualified(absolutePath)
            || !absolutePath.StartsWith(Path.DirectorySeparatorChar))
        {
            throw new InvalidDataException($"{label} must be an absolute path");
        }

        int current = LinuxNative.open(
            Path.DirectorySeparatorChar.ToString(),
            LinuxNative.OpenReadOnly
            | LinuxNative.OpenCloseOnExec
            | LinuxNative.OpenNoFollow
            | LinuxNative.OpenDirectory);
        if (current < 0)
        {
            throw new InvalidDataException($"{label} is unavailable");
        }

        try
        {
            foreach (string component in absolutePath.Split(
                         Path.DirectorySeparatorChar,
                         StringSplitOptions.RemoveEmptyEntries))
            {
                ValidateSingleComponent(component, label);
                int next = LinuxNative.openat(
                    current,
                    component,
                    LinuxNative.OpenReadOnly
                    | LinuxNative.OpenCloseOnExec
                    | LinuxNative.OpenNoFollow
                    | LinuxNative.OpenDirectory);
                if (next < 0)
                {
                    throw new InvalidDataException($"{label} has an unsafe ancestor");
                }
                NativeClose(current);
                current = next;
            }

            LinuxStatx identity = StatDescriptor(current, label);
            RequireDirectory(identity, label);
            int result = current;
            current = -1;
            return result;
        }
        finally
        {
            if (current >= 0)
            {
                NativeClose(current);
            }
        }
    }

    private static byte[] ReadRegularFile(
        int directoryDescriptor,
        string name,
        int maximumBytes,
        string label)
    {
        ValidateSingleComponent(name, label);
        int descriptor = LinuxNative.openat(
            directoryDescriptor,
            name,
            LinuxNative.OpenReadOnly
            | LinuxNative.OpenCloseOnExec
            | LinuxNative.OpenNoFollow);
        if (descriptor < 0)
        {
            throw new InvalidDataException($"{label} has unsafe file identity");
        }

        using var handle = new SafeFileHandle((IntPtr)descriptor, ownsHandle: true);
        LinuxStatx before = StatDescriptor(descriptor, label);
        RequireSingleLinkRegularFile(before, maximumBytes, label);
        VerifyFileEntry(directoryDescriptor, name, before, maximumBytes, label);

        byte[] payload = new byte[checked((int)before.Size)];
        using (var stream = new FileStream(
                   handle,
                   FileAccess.Read,
                   bufferSize: 64 * 1024,
                   isAsync: false))
        {
            stream.ReadExactly(payload);
            if (stream.ReadByte() != -1)
            {
                throw new InvalidDataException($"{label} changed during stable read");
            }

            LinuxStatx after = StatDescriptor(descriptor, label);
            RequireSingleLinkRegularFile(after, maximumBytes, label);
            if (!SameFileIdentity(before, after))
            {
                throw new InvalidDataException($"{label} changed during stable read");
            }
            VerifyFileEntry(directoryDescriptor, name, after, maximumBytes, label);
        }
        return payload;
    }

    private static void VerifyFileEntry(
        int directoryDescriptor,
        string name,
        LinuxStatx descriptorIdentity,
        int maximumBytes,
        string label)
    {
        LinuxStatx pathIdentity = StatEntry(directoryDescriptor, name, label);
        RequireSingleLinkRegularFile(pathIdentity, maximumBytes, label);
        if (!SameFileIdentity(descriptorIdentity, pathIdentity))
        {
            throw new InvalidDataException($"{label} changed during stable read");
        }
    }

    private static void VerifyDirectoryEntry(
        int parentDescriptor,
        string name,
        LinuxStatx descriptorIdentity,
        string label)
    {
        LinuxStatx pathIdentity = StatEntry(parentDescriptor, name, label);
        RequireDirectory(pathIdentity, label);
        if (!SameDirectoryIdentity(descriptorIdentity, pathIdentity))
        {
            throw new InvalidDataException($"{label} changed during authentication");
        }
    }

    private static LinuxStatx StatDescriptor(int descriptor, string label)
    {
        int result = LinuxNative.statx(
            descriptor,
            string.Empty,
            LinuxNative.AtEmptyPath | LinuxNative.AtNoAutomount,
            LinuxNative.StatxBasicStats | LinuxNative.StatxMountId,
            out LinuxStatx metadata);
        return result == 0 && HasRequiredIdentity(metadata)
            ? metadata
            : throw new InvalidDataException($"{label} identity is unavailable");
    }

    private static LinuxStatx StatEntry(int parentDescriptor, string name, string label)
    {
        int result = LinuxNative.statx(
            parentDescriptor,
            name,
            LinuxNative.AtSymlinkNoFollow | LinuxNative.AtNoAutomount,
            LinuxNative.StatxBasicStats | LinuxNative.StatxMountId,
            out LinuxStatx metadata);
        return result == 0 && HasRequiredIdentity(metadata)
            ? metadata
            : throw new InvalidDataException($"{label} identity is unavailable");
    }

    private static bool HasRequiredIdentity(LinuxStatx metadata)
        => (metadata.Mask & LinuxNative.StatxBasicStats) == LinuxNative.StatxBasicStats;

    private static void RequireDirectory(LinuxStatx metadata, string label)
    {
        if ((metadata.Mode & LinuxNative.FileTypeMask) != LinuxNative.DirectoryType)
        {
            throw new InvalidDataException($"{label} is not a real directory");
        }
    }

    private static void RequireSingleLinkRegularFile(
        LinuxStatx metadata,
        int maximumBytes,
        string label)
    {
        if ((metadata.Mode & LinuxNative.FileTypeMask) != LinuxNative.RegularFileType
            || metadata.LinkCount != 1
            || metadata.Size < 1
            || metadata.Size > (ulong)maximumBytes)
        {
            throw new InvalidDataException($"{label} has unsafe file identity");
        }
    }

    private static bool SameDirectoryIdentity(LinuxStatx left, LinuxStatx right)
        => left.DeviceMajor == right.DeviceMajor
           && left.DeviceMinor == right.DeviceMinor
           && left.Inode == right.Inode
           && left.MountId == right.MountId
           && left.Mode == right.Mode;

    private static bool SameFileIdentity(LinuxStatx left, LinuxStatx right)
        => SameDirectoryIdentity(left, right)
           && left.LinkCount == right.LinkCount
           && left.Size == right.Size
           && left.ModifiedAt.Seconds == right.ModifiedAt.Seconds
           && left.ModifiedAt.Nanoseconds == right.ModifiedAt.Nanoseconds
           && left.ChangedAt.Seconds == right.ChangedAt.Seconds
           && left.ChangedAt.Nanoseconds == right.ChangedAt.Nanoseconds;

    private static void ValidateSingleComponent(string value, string label)
    {
        if (string.IsNullOrWhiteSpace(value)
            || value is "." or ".."
            || value.Contains(Path.DirectorySeparatorChar)
            || value.Contains(Path.AltDirectorySeparatorChar))
        {
            throw new InvalidDataException($"{label} path component is invalid");
        }
    }

    private static void NativeClose(int descriptor)
    {
        if (descriptor >= 0)
        {
            _ = LinuxNative.close(descriptor);
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct LinuxStatxTimestamp
    {
        public long Seconds;
        public uint Nanoseconds;
        private readonly int _reserved;
    }

    [StructLayout(LayoutKind.Sequential, Size = 256)]
    internal struct LinuxStatx
    {
        public uint Mask;
        public uint BlockSize;
        public ulong Attributes;
        public uint LinkCount;
        public uint UserId;
        public uint GroupId;
        public ushort Mode;
        private readonly ushort _spare0;
        public ulong Inode;
        public ulong Size;
        public ulong Blocks;
        public ulong AttributesMask;
        public LinuxStatxTimestamp AccessedAt;
        public LinuxStatxTimestamp CreatedAt;
        public LinuxStatxTimestamp ChangedAt;
        public LinuxStatxTimestamp ModifiedAt;
        public uint RdevMajor;
        public uint RdevMinor;
        public uint DeviceMajor;
        public uint DeviceMinor;
        public ulong MountId;
        public uint DirectIoMemoryAlignment;
        public uint DirectIoOffsetAlignment;
    }

    private static class LinuxNative
    {
        public const int OpenReadOnly = 0;
        public const int OpenDirectory = 0x00010000;
        public const int OpenNoFollow = 0x00020000;
        public const int OpenCloseOnExec = 0x00080000;
        public const int AtSymlinkNoFollow = 0x100;
        public const int AtNoAutomount = 0x800;
        public const int AtEmptyPath = 0x1000;
        public const uint StatxBasicStats = 0x07ff;
        public const uint StatxMountId = 0x1000;
        public const ushort FileTypeMask = 0xf000;
        public const ushort DirectoryType = 0x4000;
        public const ushort RegularFileType = 0x8000;

        [DllImport("libc", SetLastError = true)]
        public static extern int open(string path, int flags);

        [DllImport("libc", SetLastError = true)]
        public static extern int openat(int directoryDescriptor, string path, int flags);

        [DllImport("libc", SetLastError = true)]
        public static extern int close(int descriptor);

        [DllImport("libc", SetLastError = true)]
        public static extern int statx(
            int directoryDescriptor,
            string path,
            int flags,
            uint mask,
            out LinuxStatx metadata);
    }
}
