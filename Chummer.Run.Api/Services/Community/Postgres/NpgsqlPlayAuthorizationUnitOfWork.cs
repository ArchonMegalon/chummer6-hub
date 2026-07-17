using System.Data;
using Npgsql;

namespace Chummer.Run.Api.Services.Community.Postgres;

public sealed class NpgsqlPlayAuthorizationUnitOfWorkFactory : IPlayAuthorizationPostgresUnitOfWorkFactory
{
    private readonly NpgsqlDataSource _dataSource;

    public NpgsqlPlayAuthorizationUnitOfWorkFactory(NpgsqlDataSource dataSource)
    {
        _dataSource = dataSource ?? throw new ArgumentNullException(nameof(dataSource));
    }

    public async ValueTask<IPlayAuthorizationPostgresUnitOfWork> BeginAsync(
        CancellationToken cancellationToken)
    {
        NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        try
        {
            NpgsqlTransaction transaction = await connection.BeginTransactionAsync(
                IsolationLevel.ReadCommitted,
                cancellationToken);
            return new NpgsqlPlayAuthorizationUnitOfWork(connection, transaction);
        }
        catch
        {
            await connection.DisposeAsync();
            throw;
        }
    }
}

internal sealed class NpgsqlPlayAuthorizationUnitOfWork : IPlayAuthorizationPostgresUnitOfWork
{
    private bool _completed;

    public NpgsqlPlayAuthorizationUnitOfWork(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction)
    {
        Connection = connection;
        Transaction = transaction;
    }

    public NpgsqlConnection Connection { get; }
    public NpgsqlTransaction Transaction { get; }

    public async Task CommitAsync(CancellationToken cancellationToken)
    {
        await Transaction.CommitAsync(cancellationToken);
        _completed = true;
    }

    public async Task RollbackAsync(CancellationToken cancellationToken)
    {
        if (_completed)
        {
            return;
        }

        await Transaction.RollbackAsync(cancellationToken);
        _completed = true;
    }

    public async ValueTask DisposeAsync()
    {
        await Transaction.DisposeAsync();
        await Connection.DisposeAsync();
    }
}
