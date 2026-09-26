using Parcels.Api.Events.External;

namespace Parcels.Api
{
    public static class Program
    {
        public static void UseApp(IApplicationBuilder app)
        {
            app.UseRabbitMq()
                .SubscribeEvent<OrderCreated>();
        }
    }
}
