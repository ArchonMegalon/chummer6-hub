using System.Reflection;
using System.Text.RegularExpressions;
using Chummer.Run.Api.Controllers;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Routing;
using Xunit;

namespace Chummer.Tests;

public sealed class AdminDiagnosticsAuthorizationTests
{
    [Fact]
    public void EveryRuntimeAdminActionUsesTheFreshPrivilegedBoundaryBeforePrivateReads()
    {
        AdminActionRoute[] adminActions = DiscoverRuntimeAdminActions();
        Assert.NotEmpty(adminActions);

        foreach (AdminActionRoute route in adminActions)
        {
            string controller = ReadControllerSource(route.ControllerType);
            string action = ExtractAction(controller, route.Method.Name);
            int headers = action.IndexOf("ApplyPrivateAdminDocumentHeaders();", StringComparison.Ordinal);
            int authorization = action.IndexOf("RequirePrivilegedAdminSubjectAsync(cancellationToken)", StringComparison.Ordinal);
            int failClosed = action.IndexOf("if (subject is null)", StringComparison.Ordinal);
            int signature = action.IndexOf(route.Method.Name, StringComparison.Ordinal);
            int bodyStart = action.IndexOf('{', signature);
            int tryStart = action.IndexOf("try", bodyStart, StringComparison.Ordinal);

            Assert.True(headers >= 0, $"{route.Route} must apply private admin response headers.");
            Assert.True(authorization > headers, $"{route.Route} must authorize after applying private response headers.");
            Assert.True(failClosed > authorization, $"{route.Route} must fail closed after fresh privileged authorization.");
            Assert.True(bodyStart >= 0 && tryStart > bodyStart, $"{route.Route} must use the standard fail-closed action shape.");

            string preAuthorizationPreamble = action[(bodyStart + 1)..tryStart];
            preAuthorizationPreamble = Regex.Replace(
                preAuthorizationPreamble,
                @"ApplyPrivateAdminDocumentHeaders\(\);\s*",
                string.Empty,
                RegexOptions.CultureInvariant);
            preAuthorizationPreamble = Regex.Replace(
                preAuthorizationPreamble,
                "const\\s+string\\s+currentPath\\s*=\\s*\"[^\"]+\";\\s*",
                string.Empty,
                RegexOptions.CultureInvariant);
            Assert.True(
                string.IsNullOrWhiteSpace(preAuthorizationPreamble),
                $"{route.Route} must not read data before entering the privileged authorization block.");
            Assert.Matches(
                @"^try\s*\{\s*var\s+subject\s*=\s*await\s+RequirePrivilegedAdminSubjectAsync\(cancellationToken\)",
                action[tryStart..failClosed]);
            Assert.Contains("return NotFound();", action[failClosed..], StringComparison.Ordinal);

            Match? prematurePrivateRead = Regex.Matches(
                    action,
                    @"(?<![A-Za-z0-9])(?<field>_[A-Za-z][A-Za-z0-9]*)\.",
                    RegexOptions.CultureInvariant)
                .Cast<Match>()
                .FirstOrDefault(match => match.Index < authorization);
            Assert.Null(prematurePrivateRead);

            ResponseCacheAttribute? cache = route.Method.GetCustomAttribute<ResponseCacheAttribute>(inherit: true);
            Assert.NotNull(cache);
            Assert.True(cache.NoStore, $"{route.Route} must disable browser and shared caching.");
            Assert.Equal(ResponseCacheLocation.None, cache.Location);
        }
    }

    [Fact]
    public void PrivilegedAdminBoundaryAlwaysUsesFreshIdentityAndTheOwnerPreservingPolicy()
    {
        string controller = ReadControllerSource(typeof(PublicLandingController));

        Assert.Contains(
            "AuthenticatedHubSubject subject = await _identity.RequireFreshSubjectAsync(Request, cancellationToken);",
            controller,
            StringComparison.Ordinal);
        Assert.Contains(
            "return ReleaseUploadAccessPolicy.CanAccess(subject) ? subject : null;",
            controller,
            StringComparison.Ordinal);
    }

    [Fact]
    public void RawProviderDiagnosticsRemainBehindTheOperatorBoundary()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot(
            "Chummer.Run.Api",
            "Controllers",
            "PublicLandingController.cs"));
        string providerAction = ExtractAction(controller, "AdminClickRankProviderDashboard");
        string visibilityAction = ExtractAction(controller, "AdminVisibilityDashboard");

        Assert.Contains("accountEmail = ReadString(providerVerification, \"account_email\")", providerAction, StringComparison.Ordinal);
        Assert.Contains("payload = providerVerification", providerAction, StringComparison.Ordinal);
        Assert.Contains("payload = finalVerdict", visibilityAction, StringComparison.Ordinal);
        Assert.Contains("RequirePrivilegedAdminSubjectAsync(cancellationToken)", providerAction, StringComparison.Ordinal);
        Assert.Contains("RequirePrivilegedAdminSubjectAsync(cancellationToken)", visibilityAction, StringComparison.Ordinal);
    }

    [Fact]
    public void PrivateAdminHeadersDisableSharedCachingAndReferrers()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot(
            "Chummer.Run.Api",
            "Controllers",
            "PublicLandingController.cs"));

        Assert.Contains("private void ApplyPrivateAdminDocumentHeaders()", controller, StringComparison.Ordinal);
        Assert.Contains("PrivateResponseCacheHeaders.Apply(Response.Headers);", controller, StringComparison.Ordinal);
        Assert.Contains("Response.Headers[\"Referrer-Policy\"] = \"no-referrer\";", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void AdminPathIsWiredIntoTheCentralPrivateResponseBoundary()
    {
        string program = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs"));

        Assert.True(
            program.Split("PrivateResponseCacheHeaders.IsPrivateAdminSurface", StringSplitOptions.None).Length >= 3,
            "Program must apply both central no-store and no-referrer handling to /admin paths.");
    }

    private static string ExtractAction(string controller, string actionName)
    {
        int signature = controller.IndexOf(actionName, StringComparison.Ordinal);
        Assert.True(signature >= 0, $"Missing action {actionName}.");

        int actionStart = controller.LastIndexOf("\n    [Http", signature, StringComparison.Ordinal);
        if (actionStart < 0)
        {
            actionStart = signature;
        }

        int nextAction = controller.IndexOf("\n    [Http", signature + actionName.Length, StringComparison.Ordinal);
        return nextAction < 0
            ? controller[actionStart..]
            : controller[actionStart..nextAction];
    }

    private static AdminActionRoute[] DiscoverRuntimeAdminActions()
    {
        var routes = new List<AdminActionRoute>();
        Type controllerBase = typeof(ControllerBase);
        foreach (Type controllerType in typeof(PublicLandingController).Assembly.GetTypes()
                     .Where(type => !type.IsAbstract && controllerBase.IsAssignableFrom(type)))
        {
            IRouteTemplateProvider?[] controllerRoutes = controllerType
                .GetCustomAttributes(inherit: true)
                .OfType<IRouteTemplateProvider>()
                .Cast<IRouteTemplateProvider?>()
                .DefaultIfEmpty(null)
                .ToArray();

            foreach (MethodInfo method in controllerType.GetMethods(
                         BindingFlags.Instance | BindingFlags.Public | BindingFlags.DeclaredOnly))
            {
                if (method.IsSpecialName || method.GetCustomAttribute<NonActionAttribute>(inherit: true) is not null)
                {
                    continue;
                }

                IRouteTemplateProvider?[] actionRoutes = method
                    .GetCustomAttributes(inherit: true)
                    .OfType<IRouteTemplateProvider>()
                    .Cast<IRouteTemplateProvider?>()
                    .DefaultIfEmpty(null)
                    .ToArray();

                foreach (IRouteTemplateProvider? controllerRoute in controllerRoutes)
                {
                    foreach (IRouteTemplateProvider? actionRoute in actionRoutes)
                    {
                        string route = CombineRouteTemplates(controllerRoute?.Template, actionRoute?.Template);
                        if (IsAdminRoute(route))
                        {
                            routes.Add(new AdminActionRoute(controllerType, method, route));
                        }
                    }
                }
            }
        }

        return routes
            .DistinctBy(route => (route.ControllerType, route.Method, route.Route))
            .OrderBy(route => route.Route, StringComparer.OrdinalIgnoreCase)
            .ThenBy(route => route.Method.Name, StringComparer.Ordinal)
            .ToArray();
    }

    private static string ReadControllerSource(Type controllerType)
    {
        string path = RepoPaths.FromRoot(
            "Chummer.Run.Api",
            "Controllers",
            $"{controllerType.Name}.cs");
        Assert.True(File.Exists(path), $"Controller source not found for {controllerType.FullName}: {path}");
        return File.ReadAllText(path);
    }

    private static string CombineRouteTemplates(string? controllerTemplate, string? actionTemplate)
    {
        string action = actionTemplate?.Trim() ?? string.Empty;
        if (action.StartsWith("~/", StringComparison.Ordinal))
        {
            return $"/{action[2..].TrimStart('/')}";
        }

        if (action.StartsWith("/", StringComparison.Ordinal))
        {
            return $"/{action.TrimStart('/')}";
        }

        string controller = controllerTemplate?.Trim().Trim('/') ?? string.Empty;
        string relativeAction = action.Trim('/');
        string combined = string.Join("/", new[] { controller, relativeAction }
            .Where(segment => !string.IsNullOrWhiteSpace(segment)));
        return $"/{combined}";
    }

    private static bool IsAdminRoute(string route)
        => route.Equals("/admin", StringComparison.OrdinalIgnoreCase)
           || route.StartsWith("/admin/", StringComparison.OrdinalIgnoreCase);

    private sealed record AdminActionRoute(Type ControllerType, MethodInfo Method, string Route);
}
